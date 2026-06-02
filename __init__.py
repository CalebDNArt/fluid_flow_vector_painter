#Flow Map Painter. A free blender addon to paint fluid flow maps on meshes
#Copyright (C) 2026 DNArt

#This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

#This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

#You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.

import bpy
import bmesh
import math
from mathutils import Vector
from mathutils import kdtree
from bpy_extras import view3d_utils
import gpu
from gpu_extras.batch import batch_for_shader

class FlowPaintOperator(bpy.types.Operator):
    bl_idname = "paint.flow_vertex"
    bl_label = "Fluid Flow Vertex Paint"
    bl_description = "Begin the flow paint operation\nClick and drag to paint\nHold SHIFT to blur\nHold CTRL to erase to neutral\nPress ESC or 'Stop Flow Painting' to stop operator"
    bl_options = {'REGISTER', 'UNDO'}
    
    def draw_cursor(self, context):
        if not context.scene.is_flow_painting or not hasattr(self, "mouse_pos"): 
            return
        
        if not (0 <= self.mouse_pos.x <= context.region.width and \
                0 <= self.mouse_pos.y <= context.region.height):
            return
        
        scene = context.scene
        
        radius = scene.flow_brush_size if not scene.flow_brush_size_pressure else scene.flow_brush_size * self.pressure
        hardness = scene.flow_brush_hardness
        core_radius = radius * hardness
        
        center = self.mouse_pos
        
        import math
        segments = 40
        outer_coords = []
        inner_coords = []
        
        for i in range(segments):
            angle = (i * 2 * math.pi) / segments
            
            outer_coords.append((
                center.x + math.cos(angle) * radius, 
                center.y + math.sin(angle) * radius
            ))

            inner_coords.append((
                center.x + math.cos(angle) * core_radius, 
                center.y + math.sin(angle) * core_radius
            ))
            
        outer_coords.append(outer_coords[0])
        inner_coords.append(inner_coords[0])
        
        shader = gpu.shader.from_builtin('UNIFORM_COLOR') if bpy.app.version >= (3, 0, 0) else gpu.shader.from_builtin('2D_UNIFORM_COLOR')
        
        outer_batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": outer_coords})
        inner_batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": inner_coords})
        
        gpu.state.blend_set('ALPHA')
        shader.bind()
        
        custom_color = (0.0, 0.0, scene.flow_brush_strength, scene.flow_brush_opacity)
        shader.uniform_float("color", custom_color) 
        
        outer_batch.draw(shader)
        
        if hardness < 1.0 and hardness > 0.0:
            inner_batch.draw(shader)
            
        gpu.state.blend_set('NONE')
    
    def cleanup(self, context):
        if hasattr(self, "_handle") and self._handle:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            self._handle = None
        context.scene.is_flow_painting = False
        
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()
                
        if getattr(self, 'original_mode', None) and context.active_object:
            try:
                bpy.ops.object.mode_set(mode=self.original_mode)
            except Exception as e:
                print(f"Could not restore mode: {e}")

    def invoke(self, context, event):
        if context.scene.is_flow_painting:
            self.cleanup(context)
            return {'FINISHED'}

        self.obj = context.active_object
        if not self.obj or self.obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh")
            return {'CANCELLED'}
        
        mesh = self.obj.data
        
        self.color_layer = mesh.color_attributes.get("Flow")

        if self.color_layer is None:
            self.color_layer = mesh.color_attributes.new(
                name="Flow",
                type='FLOAT_COLOR',
                domain='POINT'
            )
            
            for datum in self.color_layer.data:
                datum.color = (0.5, 0.5, 0.0, 1.0)
        
        mw = self.obj.matrix_world
        normal_matrix = mw.to_3x3()        
                
        mesh.color_attributes.active_color = self.color_layer
        
        size = len(self.obj.data.vertices)
        
        self.world_positions = [None] * size
        self.world_normals = [None] * size
        
        self.kd = kdtree.KDTree(size)
        for i, v in enumerate(self.obj.data.vertices):
            world_pos = mw @ v.co
            world_normal = (normal_matrix @ v.normal).normalized()
            
            self.world_positions[i] = world_pos
            self.world_normals[i] = world_normal
            
            self.kd.insert(v.co, i)
        self.kd.balance()
        
        self.original_mode = None
        
        if context.active_object:
            self.original_mode = bpy.context.object.mode
        bpy.ops.object.mode_set(mode="VERTEX_PAINT")

        self.prev_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        self.mouse_pos = self.prev_mouse
        self.is_painting = False
        context.scene.is_flow_painting = True

        self._handle = bpy.types.SpaceView3D.draw_handler_add(self.draw_cursor, (context,), 'WINDOW', 'POST_PIXEL')

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not context.scene.is_flow_painting:
            self.cleanup(context)
            return {'FINISHED'}
            
        if event.type == 'ESC' and event.value == 'RELEASE':
            self.cleanup(context)
            return {'FINISHED'}
            
        is_over_ui = False
        if not (context.area.x <= event.mouse_x <= context.area.x + context.area.width and \
                context.area.y <= event.mouse_y <= context.area.y + context.area.height):
            is_over_ui = True
        else:
            for region in context.area.regions:
                if region.type in {'UI', 'TOOLS', 'HEADER', 'FOOTER', 'TOOL_HEADER'}:
                    if (region.x <= event.mouse_x <= region.x + region.width) and \
                       (region.y <= event.mouse_y <= region.y + region.height):
                        is_over_ui = True
                        break

        if is_over_ui and not self.is_painting:
            if event.type in {'LEFTMOUSE', 'MIDDLEMOUSE', 'RIGHTMOUSE', 'MOUSEMOVE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
                return {'PASS_THROUGH'}
                
        if event.type == "MOUSEMOVE":
            self.mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
            if context.area:
                context.area.tag_redraw()

        if event.type == "LEFTMOUSE":
            if event.value == "PRESS":
                self.is_painting = True
                self.prev_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            elif event.value == "RELEASE":
                self.is_painting = False
            
        if event.type == "MOUSEMOVE" and self.is_painting:

            scene = context.scene
            self.pressure = getattr(event, "pressure", 1.0)
            self.radius = scene.flow_brush_size if not scene.flow_brush_size_pressure else scene.flow_brush_size * self.pressure
            self.strength_value = scene.flow_brush_strength if not scene.flow_brush_strength_pressure else scene.flow_brush_strength * self.pressure
            self.opacity = scene.flow_brush_opacity if not scene.flow_brush_opacity_pressure else scene.flow_brush_opacity * self.pressure
            self.hardness = scene.flow_brush_hardness if not scene.flow_brush_hardness_pressure else scene.flow_brush_hardness * self.pressure

            current_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            
            if event.ctrl:
                self.paint_vertices(context, current_mouse, 0.5, 0.5, erase=True)
            elif event.shift:
                self.blur_vertices(context, current_mouse)
            else:
                delta = current_mouse - self.prev_mouse
                if delta.length > 1:
                    flow = delta.normalized()
                    self.flow_r = (flow.x * 0.5 + 0.5)
                    self.flow_g = (flow.y * 0.5 + 0.5)
                    self.paint_vertices(context, current_mouse, self.flow_r, self.flow_g)
                    self.prev_mouse = current_mouse
                
        if event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE", "W", "S"}:
            if event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE"} and not (event.shift or event.ctrl or event.alt):
                return {'PASS_THROUGH'}
            if event.type == "MIDDLEMOUSE" and event.shift:
                return {'PASS_THROUGH'}
                
            if event.type == "WHEELUPMOUSE" or event.type == "W":
                if event.shift: context.scene.flow_brush_strength = min(1.0, context.scene.flow_brush_strength + 0.05)
                elif event.ctrl: context.scene.flow_brush_hardness = min(1.0, context.scene.flow_brush_hardness + 0.05)
                elif event.alt: context.scene.flow_brush_opacity = min(1.0, context.scene.flow_brush_opacity + 0.05)          
                elif event.type == "W": context.scene.flow_brush_size += 1
                        
            elif event.type == "WHEELDOWNMOUSE" or event.type == "S":
                if event.shift: context.scene.flow_brush_strength = max(0.0, context.scene.flow_brush_strength - 0.05)
                elif event.ctrl: context.scene.flow_brush_hardness = max(0.0, context.scene.flow_brush_hardness - 0.05)
                elif event.alt: context.scene.flow_brush_opacity = max(0.0, context.scene.flow_brush_opacity - 0.05)          
                elif event.type == "S": context.scene.flow_brush_size = max(1, context.scene.flow_brush_size - 1)
                    
            if context.area:
                context.area.tag_redraw()

        if event.type not in {'LEFTMOUSE', 'MOUSEMOVE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'W', 'S', 'ESC'}:
            return {'PASS_THROUGH'}

        return {'RUNNING_MODAL'}
    
    def get_brush_world_radius(self, context, mouse_pos, hit_location):
        region = context.region
        rv3d = context.space_data.region_3d

        edge_pos = mouse_pos + Vector((self.radius, 0))

        edge_world = view3d_utils.region_2d_to_location_3d(
            region,
            rv3d,
            edge_pos,
            hit_location
        )

        return (edge_world - hit_location).length
    
    def paint_vertices(self, context, mouse_pos, r, g, erase=False):
        mesh = self.obj.data
        color_layer = self.color_layer
        
        region = context.region
        rv3d = context.space_data.region_3d

        origin = view3d_utils.region_2d_to_origin_3d(
            region,
            rv3d,
            mouse_pos
        )

        direction = view3d_utils.region_2d_to_vector_3d(
            region,
            rv3d,
            mouse_pos
        )

        success, location, normal, face_index, obj, matrix = (
            context.scene.ray_cast(
                context.view_layer.depsgraph,
                origin,
                direction
            )
        )

        if not success:
            return
        
        world_radius = self.get_brush_world_radius(
            context,
            mouse_pos,
            location
        )

        core_radius = world_radius * self.hardness

        verts = self.kd.find_range(
            location,
            world_radius
        )
        

        for world_pos, vert_index, dist in verts:
            offset = world_pos - location
            
            if offset.dot(normal) < 0 and context.scene.surface_side_filter:
                continue
                
            vert_normal = self.world_normals[vert_index]
            
            if vert_normal.dot(normal) < math.cos(context.scene.normal_filter_angle * (math.pi / 180.0)) and context.scene.normal_filter:
                continue    
                
            if dist <= core_radius:
                falloff = 1.0
            else:

                if world_radius == core_radius:
                    falloff = 1.0
                else:
                    falloff = 1.0 - (
                        (dist - core_radius)
                        / (world_radius - core_radius)
                    )

                    falloff *= falloff

            color = color_layer.data[vert_index].color

            existing = Vector((
                color[0],
                color[1],
                color[2]
            ))

            new = Vector((
                1.0 - r if context.scene.invert_r else r,
                1.0 - g if context.scene.invert_g else g,
                1.0 - self.strength_value if context.scene.invert_b else self.strength_value
            ))

            if erase:
                new.z = 0.0 if context.scene.invert_b else 1.0

            blend = falloff * self.opacity

            if context.scene.brush_r:
                color[0] = existing.x + (new.x - existing.x) * blend

            if context.scene.brush_g:
                color[1] = existing.y + (new.y - existing.y) * blend

            if context.scene.brush_b:
                color[2] = existing.z + (new.z - existing.z) * blend

            color_layer.data[vert_index].color = color

        mesh.update()
        
    def blur_vertices(self, context, mouse_pos):
        mesh = self.obj.data
        color_layer = self.color_layer

        if not color_layer:
            return

        region = context.region
        rv3d = context.space_data.region_3d

        origin = view3d_utils.region_2d_to_origin_3d(
            region,
            rv3d,
            mouse_pos
        )

        direction = view3d_utils.region_2d_to_vector_3d(
            region,
            rv3d,
            mouse_pos
        )

        success, location, normal, face_index, obj, matrix = (
            context.scene.ray_cast(
                context.view_layer.depsgraph,
                origin,
                direction
            )
        )

        if not success:
            return

        world_radius = self.get_brush_world_radius(
            context,
            mouse_pos,
            location
        )

        core_radius = world_radius * self.hardness

        verts = self.kd.find_range(
            location,
            world_radius
        )

        verts_in_radius = []
        avg_color = Vector((0.0, 0.0, 0.0))
        total_weight = 0.0

        for world_pos, vert_index, dist in verts:
            offset = world_pos - location

            if offset.dot(normal) < 0 and context.scene.surface_side_filter:
                continue

            vert_normal = self.world_normals[vert_index]

            if vert_normal.dot(normal) < math.cos(context.scene.normal_filter_angle * (math.pi / 180)) and context.scene.normal_filter:
                continue
            
            if dist <= core_radius:
                falloff = 1.0
            else:

                if world_radius == core_radius:
                    falloff = 1.0
                else:
                    falloff = 1.0 - (
                        (dist - core_radius)
                        / (world_radius - core_radius)
                    )

                    falloff *= falloff

            weight = falloff * self.opacity

            verts_in_radius.append(
                (vert_index, weight)
            )

            c = color_layer.data[vert_index].color

            avg_color += Vector((
                c[0],
                c[1],
                c[2]
            )) * weight
            
            total_weight += weight
            
        if not verts_in_radius:
            return      
        
        if total_weight <= 0:
            return
        
        avg_color /= total_weight

        for vert_index, weight in verts_in_radius:

            color = color_layer.data[vert_index].color

            existing = Vector((
                color[0],
                color[1],
                color[2]
            ))

            if context.scene.brush_r:
                color[0] = existing.x + (
                    avg_color.x - existing.x
                ) * weight

            if context.scene.brush_g:
                color[1] = existing.y + (
                    avg_color.y - existing.y
                ) * weight

            if context.scene.brush_b:
                color[2] = existing.z + (
                    avg_color.z - existing.z
                ) * weight

            color_layer.data[vert_index].color = color

        mesh.update()
        
class FlowPaintSmoothOperator(bpy.types.Operator):
    bl_idname = "paint.flow_smooth_all"
    bl_label = "Smooth Flow Map"
    bl_description = "Average the selected channels across the entire mesh by a number of iterations.\n⚠ For large meshes and/or high iterations this operation could take awhile ⚠"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object

        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh to smooth.")
            return {'CANCELLED'}

        mesh = obj.data
        
        if not mesh.color_attributes.active_color:
            self.report({'ERROR'}, "No active color attribute found.")
            return {'CANCELLED'}
            
        color_layer = mesh.color_attributes.active_color

        neighbors = {v.index: [] for v in mesh.vertices}
        for edge in mesh.edges:
            neighbors[edge.vertices[0]].append(edge.vertices[1])
            neighbors[edge.vertices[1]].append(edge.vertices[0])

        iterations = context.scene.flow_smooth_iterations

        mask_r = context.scene.flow_smooth_r
        mask_g = context.scene.flow_smooth_g
        mask_b = context.scene.flow_smooth_b

        for _ in range(iterations):
            new_colors = {}
            
            for vert in mesh.vertices:
                orig_color = color_layer.data[vert.index].color
                
                o_x = ((1.0 - orig_color[0]) * 2.0) - 1.0 if context.scene.invert_r else (orig_color[0] * 2.0) - 1.0
                o_y = ((1.0 - orig_color[1]) * 2.0) - 1.0 if context.scene.invert_g else (orig_color[1] * 2.0) - 1.0
                orig_dir = Vector((o_x, o_y))
                orig_strength = orig_color[2]

                vec_sum = orig_dir.copy()
                strength_sum = orig_strength
                count = 1

                for n_idx in neighbors[vert.index]:
                    n_color = color_layer.data[n_idx].color
                    n_x = ((1.0 - n_color[0]) * 2.0) - 1.0 if context.scene.invert_r else (n_color[0] * 2.0) - 1.0
                    n_y = ((1.0 - n_color[1]) * 2.0) - 1.0 if context.scene.invert_g else (n_color[1] * 2.0) - 1.0
                    n_dir = Vector((n_x, n_y))
                    vec_sum += n_dir
                    strength_sum += n_color[2]
                    count += 1

                avg_dir = vec_sum / count
                if avg_dir.length < 0.001:
                    avg_dir = Vector((0.0, 0.0))

                final_x = avg_dir.x if mask_r else orig_dir.x
                final_y = avg_dir.y if mask_g else orig_dir.y
                final_strength = (strength_sum / count) if mask_b else orig_strength
                
                masked_dir = Vector((final_x, final_y))

                pack_x = masked_dir.x * 0.5 + 0.5
                pack_x = 1.0 - pack_x if context.scene.invert_r else pack_x
                
                pack_y = masked_dir.y * 0.5 + 0.5
                pack_y = 1.0 - pack_y if context.scene.invert_g else pack_y
                
                pack_b = 1.0 - final_strength if context.scene.invert_b else final_strength

                new_colors[vert.index] = (pack_x, pack_y, pack_b, 1.0)

            for idx, color_data in new_colors.items():
                color_layer.data[idx].color = color_data

        mesh.update()
        return {'FINISHED'}

class FlowPaintResetOperator(bpy.types.Operator):
    bl_idname = "paint.flow_reset"
    bl_label = "Reset Flow Map"
    bl_description = "Reset all vertices on the mesh to R=0.5, G=0.5, B=0.0/1.0 (No flow direction, zero strength)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH': return {'CANCELLED'}

        mesh = obj.data
        color_layer = mesh.color_attributes.active_color
        
        if not color_layer:
            self.report({'ERROR'}, "No active color attribute found.")
            return {'CANCELLED'}

        for datum in color_layer.data:
            if context.scene.invert_b:
                datum.color = (0.5, 0.5, 0.0, 1.0)
            else:
                datum.color = (0.5, 0.5, 1.0, 1.0)
            
        mesh.update()
        return {'FINISHED'}

class FLOWPAINT_PT_panel(bpy.types.Panel):
    bl_label = "Flow Paint"
    bl_idname = "FLOWPAINT_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Flow Paint'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        #Main
        box = layout.box()
        if not scene.is_flow_painting:
            box.operator("paint.flow_vertex",text="Start Flow Painting", icon = "BRUSH_DATA")
            row = box.row(align=True)
            row.prop(scene, "invert_r", toggle=True)
            row.prop(scene, "invert_g", toggle=True)
            row.prop(scene, "invert_b", toggle=True)       
            box.operator("paint.flow_reset", text = "Fill Neutral", icon = "X")
            box.prop(scene, "surface_side_filter", toggle=True)
            row = box.row(align=True)
            row.prop(scene, "normal_filter", toggle=True)
            if scene.normal_filter:
                row.prop(scene, "normal_filter_angle", slider=True)
        else:
            box.operator("paint.flow_vertex", text="Stop Flow Painting", icon="CANCEL", depress=True)
        
        #Brush
        layout.separator()
        box = layout.box()
        title_row = box.row()
        title_row.label(text = "Brush Settings")
        row = box.row(align = True)
        row.prop(scene, "flow_brush_size", slider = True)
        row.prop(scene, "flow_brush_size_pressure", toggle = True, icon = "STYLUS_PRESSURE")
        row = box.row(align = True)
        row.prop(scene, "flow_brush_strength")
        row.prop(scene, "flow_brush_strength_pressure", toggle = True, icon = "STYLUS_PRESSURE")
        row = box.row(align = True)
        row.prop(scene, "flow_brush_opacity")
        row.prop(scene, "flow_brush_opacity_pressure", toggle = True, icon = "STYLUS_PRESSURE")
        row = box.row(align = True)
        row.prop(scene, "flow_brush_hardness")
        row.prop(scene, "flow_brush_hardness_pressure", toggle = True, icon = "STYLUS_PRESSURE")
        row = box.row(align=True)
        row.prop(scene, "brush_r", toggle=True)
        row.prop(scene, "brush_g", toggle=True)
        row.prop(scene, "brush_b", toggle=True)
        layout.separator()
        
        #Smoothing
        box = layout.box()
        title_row = box.row()
        title_row.label(text = "Color Smoothing Settings")
        box.operator("paint.flow_smooth_all", text="Smooth Entire Mesh")
        row = box.row(align=True)
        row.prop(scene, "flow_smooth_r", toggle=True)
        row.prop(scene, "flow_smooth_g", toggle=True)
        row.prop(scene, "flow_smooth_b", toggle=True)
        box.prop(scene, "flow_smooth_iterations")
        layout.separator()
        
        #Vertex Visualizer
        box = layout.box()
        title_row = box.row()
        title_row.label(text = "Flow Vector Display Settings")
        box.prop(scene, "flow_show_vectors", text="Show Flow Vectors", toggle=True, icon='VIEW3D')
        
        if scene.flow_show_vectors:
            col = box.column(align=True)
            col.prop(scene, "flow_vector_length", slider=True)
            col.prop(scene, "flow_vector_color", text="")


classes = (
    FlowPaintOperator,
    FlowPaintSmoothOperator,
    FlowPaintResetOperator,
    FLOWPAINT_PT_panel,
)

draw_handler = None

def draw_flow_vectors():
    context = bpy.context
    scene = context.scene
    
    if not getattr(scene, "flow_show_vectors", False): return
    
    obj = context.active_object
    if not obj or obj.type != 'MESH': return

    mesh = obj.data
    color_layer = mesh.color_attributes.active_color
    if not color_layer: return

    mw = obj.matrix_world
    lines = []
    colors = []
    
    scale = scene.flow_vector_length
    user_color = scene.flow_vector_color

    for vert in mesh.vertices:
        c = color_layer.data[vert.index].color
        
        strength = 1.0 - c[2] if scene.invert_b else c[2]
        if strength < 0.05: continue

        dir_x = ((1.0 - c[0]) * 2.0) - 1.0 if scene.invert_r else (c[0] * 2.0) - 1.0
        dir_y = ((1.0 - c[1]) * 2.0) - 1.0 if scene.invert_g else (c[1] * 2.0) - 1.0
        
        flow_vec = Vector((dir_x, dir_y, 0.0)) 
        
        start_pos = mw @ vert.co
        end_pos = start_pos + (mw.to_3x3() @ flow_vec) * strength * scale
        
        lines.append(start_pos)
        lines.append(end_pos)
        
        line_color = (user_color[0] * strength, user_color[1] * strength, user_color[2] * strength, 1.0)
        colors.append(line_color)
        colors.append(line_color)

        if flow_vec.length > 0.001:
            flow_norm = flow_vec.normalized()
            
            arrow_size = 0.25 
            
            import math
            angle1 = math.radians(150)
            angle2 = math.radians(210)
            
            w1_x = flow_norm.x * math.cos(angle1) - flow_norm.y * math.sin(angle1)
            w1_y = flow_norm.x * math.sin(angle1) + flow_norm.y * math.cos(angle1)
            wing1 = Vector((w1_x, w1_y, 0.0)) * strength * scale * arrow_size
            
            w2_x = flow_norm.x * math.cos(angle2) - flow_norm.y * math.sin(angle2)
            w2_y = flow_norm.x * math.sin(angle2) + flow_norm.y * math.cos(angle2)
            wing2 = Vector((w2_x, w2_y, 0.0)) * strength * scale * arrow_size
            
            wing1_pos = end_pos + (mw.to_3x3() @ wing1)
            wing2_pos = end_pos + (mw.to_3x3() @ wing2)
            
            lines.append(end_pos)
            lines.append(wing1_pos)
            colors.append(line_color)
            colors.append(line_color)
            
            lines.append(end_pos)
            lines.append(wing2_pos)
            colors.append(line_color)
            colors.append(line_color)

    if not lines: return

    if bpy.app.version < (3, 0, 0):
        shader = gpu.shader.from_builtin('3D_SMOOTH_COLOR')
    else:
        shader = gpu.shader.from_builtin('SMOOTH_COLOR')
    
    batch = batch_for_shader(shader, 'LINES', {"pos": lines, "color": colors})

    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(2.0)
    shader.bind()
    batch.draw(shader)
    gpu.state.blend_set('NONE')

def register():
    bpy.types.Scene.is_flow_painting = bpy.props.BoolProperty(default=False)
    
    bpy.types.Scene.surface_side_filter = bpy.props.BoolProperty(
        name="Surface-Side Filter",
        description="Filter the painting so that any verts hit must be on the same side as visible to the camera\nPrevents paint-through on 3D meshes",
        default=True
    )
    
    bpy.types.Scene.normal_filter = bpy.props.BoolProperty(
        name="Normal Filter",
        description="Filter the painting so that the normal must be within a certain angle of the cameras view ray\nPrevents painting over edges",
        default=True
    )
    
    bpy.types.Scene.normal_filter_angle = bpy.props.FloatProperty(
        name="Angle",
        description="Sets the maximum angle allowed between the normal and camera view ray for normal filtering",
        min=0.0,
        max=90.0,
        default = 45.0,
        subtype="FACTOR"
    )
    
    bpy.types.Scene.flow_smooth_iterations = bpy.props.IntProperty(
        name="Iterations",
        description="How many times to run the smoothing algorithm",
        default=5,
        min=1,
        max=50
    )
    
    bpy.types.Scene.invert_r = bpy.props.BoolProperty(
        name="Invert R (X)", 
        description="Invert R channel direction (X Flow)",
        default=False
    )
    
    bpy.types.Scene.invert_g = bpy.props.BoolProperty(
        name="Invert G (Y)", 
        description="Invert G channel direction (Y Flow)",
        default=True
    )
    
    bpy.types.Scene.invert_b = bpy.props.BoolProperty(
        name="Invert B (Strength)", 
        description="Invert B channel (Flow Strength)",
        default=True
    )
    
    bpy.types.Scene.flow_brush_size = bpy.props.IntProperty(
        name = "Brush Size",
        description = "Brush size in pixels\nUse (W/S) to control the brush size while painting",
        default = 50,
        min = 0,
        max = 250,
        subtype = "PIXEL"
    )
    
    bpy.types.Scene.flow_brush_size_pressure = bpy.props.BoolProperty(
        name = "",
        description = "Use pressure for brush size",
        default = False
    )
    
    bpy.types.Scene.flow_brush_strength = bpy.props.FloatProperty(
        name = "Brush Flow Strength",
        description = "Brush flow strength (0 = No flow, 1 = Max flow)\nUse (SHIFT + Scrollwheel Up/Down) or (SHIFT + W/S) to control the flow vector strength while painting.\n⚠ THIS IS NOT THE OPACITY FOR THE BRUSH, THIS IS FOR THE STRENGTH OF THE FLOW VECTORS ⚠",
        default = 1.0,
        min = 0.0,
        max = 1.0,
        subtype = "FACTOR"
    )
    
    bpy.types.Scene.flow_brush_strength_pressure = bpy.props.BoolProperty(
        name = "",
        description = "Use pressure for brush flow vector strength",
        default = True
    )
    
    bpy.types.Scene.flow_brush_opacity = bpy.props.FloatProperty(
        name = "Brush Opacity",
        description = "Brush opacity (0 = transparent, 1 = opaque)\nUse (ALT + Scrollwheel Up/Down) or (ALT + W/S) to control the strength while painting",
        default = 1.0,
        min = 0.0,
        max = 1.0,
        subtype = "FACTOR"
    )
    
    bpy.types.Scene.flow_brush_opacity_pressure = bpy.props.BoolProperty(
        name = "",
        description = "Use pressure for brush opacity",
        default = False
    )
    
    bpy.types.Scene.flow_brush_hardness = bpy.props.FloatProperty(
        name = "Brush Hardness",
        description = "Brush edge hardness (0 = soft, 1 = hard)\nUse (CTRL + Scrollwheel Up/Down) or (CTRL + W/S) to control the hardness while painting",
        default = 0.5,
        min = 0.0,
        max = 1.0,
        subtype = "FACTOR"
    )
    
    bpy.types.Scene.flow_brush_hardness_pressure = bpy.props.BoolProperty(
        name = "",
        description = "Use pressure for brush hardness",
        default = False
    )
    
    bpy.types.Scene.flow_show_vectors = bpy.props.BoolProperty(
        name = "Show Vectors",
        description = "Draw the flow vectors on the mesh",
        default = False
    )
    
    bpy.types.Scene.flow_vector_length = bpy.props.FloatProperty(
        name="Vector Length",
        default=0.5, 
        min=0.001, 
        max=10.0
    )
    
    bpy.types.Scene.flow_vector_color = bpy.props.FloatVectorProperty(
        name="Vector Color",
        subtype='COLOR', 
        default=(1.0, 0.8, 0.0), 
        min=0.0, 
        max=1.0, 
        size=3
    )
    
    bpy.types.Scene.flow_smooth_r = bpy.props.BoolProperty(
        name="R (X)", 
        description="Smooth R Channel (X Flow)",
        default=True
    )
    
    bpy.types.Scene.flow_smooth_g = bpy.props.BoolProperty(
        name="G (Y)", 
        description="Smooth G Channel (Y Flow)",
        default=True
    )
    
    bpy.types.Scene.flow_smooth_b = bpy.props.BoolProperty(
        name="B (Strength)", 
        description="Smooth B Channel (Flow Strength)",
        default=True
    )
    
    bpy.types.Scene.brush_r = bpy.props.BoolProperty(
        name="R (X)", 
        description="Affect R Channel (X Flow)",
        default=True
    )
    
    bpy.types.Scene.brush_g = bpy.props.BoolProperty(
        name="G (Y)", 
        description="Affect G Channel (Y Flow)",
        default=True
    )
    
    bpy.types.Scene.brush_b = bpy.props.BoolProperty(
        name="B (Strength)", 
        description="Affect B Channel (Flow Strength)",
        default=True
    )
    
    for c in classes:
        bpy.utils.register_class(c)
        
    global draw_handler
    if draw_handler is None:
        draw_handler = bpy.types.SpaceView3D.draw_handler_add(draw_flow_vectors, (), "WINDOW", "POST_VIEW")

def unregister():
    del bpy.types.Scene.is_flow_painting
    del bpy.types.Scene.surface_side_filter
    del bpy.types.Scene.normal_filter
    del bpy.types.Scene.normal_filter_angle
    
    del bpy.types.Scene.invert_r
    del bpy.types.Scene.invert_g
    del bpy.types.Scene.invert_b
    
    del bpy.types.Scene.flow_brush_size
    del bpy.types.Scene.flow_brush_size_pressure
    del bpy.types.Scene.flow_brush_strength
    del bpy.types.Scene.flow_brush_strength_pressure
    del bpy.types.Scene.flow_brush_opacity
    del bpy.types.Scene.flow_brush_opacity_pressure
    del bpy.types.Scene.flow_brush_hardness
    del bpy.types.Scene.flow_brush_hardness_pressure
    
    del bpy.types.Scene.brush_r
    del bpy.types.Scene.brush_g
    del bpy.types.Scene.brush_b

    del bpy.types.Scene.flow_show_vectors
    del bpy.types.Scene.flow_vector_length
    del bpy.types.Scene.flow_vector_color
    
    del bpy.types.Scene.flow_smooth_r
    del bpy.types.Scene.flow_smooth_g
    del bpy.types.Scene.flow_smooth_b
    del bpy.types.Scene.flow_smooth_iterations
    
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
        
    global draw_handler
    if draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(draw_handler, "WINDOW")
        draw_handler = None

if __name__ == "__main__":
    register()
