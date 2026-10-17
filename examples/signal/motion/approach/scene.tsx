import {makeScene2D, Rect, Line} from '@motion-canvas/2d';
import {createRef, waitFor} from '@motion-canvas/core';
export default makeScene2D(function* (view) {
  view.fill('#15283F');
  view.add(<Line points={[[-140,35],[-15,35]]} stroke={'#F5E9CA'} lineWidth={5}/>);
  const signal=createRef<Rect>();
  view.add(<Rect ref={signal} x={-130} y={20} width={20} height={20} fill={'#F3AE35'}/>);
  yield* signal().x(-25,1.1);
  yield* waitFor(1);
});
