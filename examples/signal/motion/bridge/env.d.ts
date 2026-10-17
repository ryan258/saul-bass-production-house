/// <reference types="vite/client" />
declare module '*?scene' {
  import {FullSceneDescription} from '@motion-canvas/core';
  const scene: FullSceneDescription;
  export default scene;
}
declare module '@motion-canvas/2d/editor' {
  import {Plugin} from '@motion-canvas/core';
  export default function editorPlugin(): Plugin;
}
