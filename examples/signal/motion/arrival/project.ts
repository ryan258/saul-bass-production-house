import {makeProject} from '@motion-canvas/core';
import scene from './scene?scene';
import editorPlugin from '@motion-canvas/2d/editor';
scene.plugins=[editorPlugin()];
export default makeProject({scenes:[scene]});
