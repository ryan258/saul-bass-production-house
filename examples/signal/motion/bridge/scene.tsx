import {makeScene2D, Rect, Line} from '@motion-canvas/2d';
import {createRef, waitFor} from '@motion-canvas/core';
export default makeScene2D(function* (view) {
  view.fill('#15283F');
  view.add(<Line points={[[-140,35],[-15,35]]} stroke={'#F5E9CA'} lineWidth={5}/>);
  view.add(<Rect x={-25} y={20} width={20} height={20} fill={'#F3AE35'}/>);
  const link=createRef<Line>();
  view.add(<Line ref={link} points={[[-15,35],[100,35]]} stroke={'#72C9B5'} lineWidth={7} end={0}/>);
  yield* link().end(1,1.1);
  yield* waitFor(1);
});
