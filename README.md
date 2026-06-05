# Fluid Flow Vertex Painter
A free Blender extension for painting fluid flow maps directly onto meshes using vertex paint.

<img width="1920" height="1009" alt="TestFlowScene2" src="https://github.com/user-attachments/assets/b91e4024-609f-4338-a8d2-b1dfaaf639bd" />

<img width="800" height="450" alt="ezgif-466748588f5c9149" src="https://github.com/user-attachments/assets/f5bf7831-7578-48c1-b6a5-cb7af1b25265" />

## Features
* Paint fluid flow vectors directly onto a mesh using vertex paint by tracking cursor direction.
* Invert individual channels to function properly with your setup.
* Paint dynamically with settings for brush size, flow strength, opacity, and hardness. All brush settings are also stylus pressure compatible. You can also control which channels to affect while painting.
* Smooth the colors across the mesh to make the flow smoother. You can smooth only specific channels.
* Display the flow vectors on the mesh. Arrows will appear pointing in the direction that the flow is pointing with length and value representative of the strength. These vectors are relative to the current channel settings.

## Installation
Install the extension by downloading from the Blender extension library. In Blender go to **Edit > Preferences > Extensions** and search for "Fluid Flow Vertex Painter". 

Alternatively, download the .zip file from the repository and go to **Edit > Preferences > Extensions**. Click the down arrow in the top right corner and select "Install from Disk". Select the .zip file to install.

## Setup
1. Create the mesh you want to paint. This tool is only designed for 2D fluid flow so the mesh should be relatively flat. Minor changes in surface height or bumpiness is okay.
2. Subdivide the mesh. As this tool is vertex paint based, the mesh should have even vertex density for the interpolation to make the flow look correct. The more subdivisions, the more detail that can be painted.
   * I recommend using a subdivided plane with the faces that won't be seen deleted.
3. Ensure that there are no active vertex color data on the object. The tool will automatically make one named "Flow", if there are multiple color data then certain engines (such as Unity) will only pull color from the data at index 0.
4. Press **N** in the 3D View to open the toolbar. Find **"Fluid Flow Vertex Painter"**
5. Set the channel inversion settings appropriate for your workflow.
6. Select the mesh you want to paint. You can be in any mode, the tool will force you into object mode and return to the original mode when terminated. The view drawing settings will automatically change to flat shading with wireframe. The settings will revert when the tool is disabled
7. Change to an orthographic axis view (Looking down X, Y, or Z). The direction painted is relative to the direction the mouse moves on the screen. If you rotate the camera while painting the directions painted will change.
8. Click **"Start Flow Painting"**. The mesh will be filled with (0.5, 0.5, 0.0/1.0 depending on if the blue channel is inverted) this defaults to zero flow anywhere on the mesh.

## Using the Tool
### Brush
#### Painting
* Use your mouse or stylus to paint on the mesh
  * **Brush Size:** the size of the brush in pixels. The brush is screen-space relative like other paint tools
    * Control the size with **W/S** (Brush size Up/Down).
  * **Brush Flow Strength:** the strength of the flow vectors painted (blue channel). This applies blue to flow vectors to control the magnitude. It is relative to the current channel inversion settings. Example: Flow Strength 1.0 = always high flow, Flow Strength 0.0 = always no flow, regardless of if the blue channel is inverted (1-0) or normal (0-1).
    * Control the flow strength with **SHIFT + W/S** or **SHIFT + Scrollwheel Up/Down**.
  * **Brush Opacity:** the opacity of the brush. Controls how strongly the brush blends with the colors below. Opacity 1.0 = Overwrite color, Opacity 0.0 = No change.
    * Control the opacity with **ALT + W/S** or **ALT + Scrollwheel Up/Down**.
  * **Brush Hardness:** the hardness of the brush. Controls how strongly the brush fades at the edges. Hardness 1.0 = Brush applies full color within the entire brush area, Hardness 0.0 = Brush smoothly falls off from the center towards the edges.
    * Control the hardness with **CTRL + W/S** or **CTRL + Scrollwheel Up/Down**
  * All brush settings are stylus pressure compatible, press the button to the right of the property to apply pressure control.
  * Select the channels you want your brush to affect. Note that unchecking the blue channel will make the brush flow strength have no effect.
#### Blurring
* Hold **SHIFT** while painting to blur the color of the vertex between itself and its neighbours
#### Clearing
* Hold **CTRL** while painting to reset the affected vertices to zero flow (0.5, 0.5, 0.0/1.0 depending on B channel inversion)

### Resetting the Mesh
* If you need to reset your mesh back to no flow click **"Fill Neutral**". This will reset all of the colors on the mesh to (0.5, 0.5, 0.0/1.0 depending on B channel settings) no direction, no flow.
  * Color should be a dark green-yellow for standard blue channel
  * Color should be a blue-purple for inverted blue channel

### Smoothing Colors
* Use this to smooth out the vertex colors across the entire mesh
  * **Channel Settings:** choose which channels the smoothing will affect.
  * **Iterations:** the number of times for the smoother to run.
  * **NOTE: that this operation requires iterating over all vertices in mesh multiple times. High density meshes and high iterations will take awhile to complete.**

### Displaying Flow Vectors
* Click **"Show Flow Vectors"** to display the vectors as arrows extending from the vertex.
  * **Vector Length:** The length of the vectors in world space units. The length set is the maximum length at highest flow, the length is multiplied by the flow strength at that vertex
  * **Vector Color:** The color of the vectors. The color is multiplied by the flow strength at that vertex. Darker color = lower flow. I recommend using a high saturation, high value color
  * **NOTE: This visualization runs on the GPU, while most PCs can handle it, I would recommend against using it with extremely high resolution meshes.**
 
### Quit Painting
Press **ESC** or **"Stop Flow Painting"** to stop the operator. Settings for drawing and mode will be reverted to before the operator started.
 
### IMPORTANT NOTE
**The tool paints the colors in LINEAR colorspace and not sRGB colorspace. If you directly use this in a shader without converting the colorspace, the directions will be skewed.**

## License
Distributed under the GPLv3 License. See 'LICENSE' for more information.
