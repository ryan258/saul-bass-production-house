import {makeScene2D, Rect, Line, Circle} from '@motion-canvas/2d';
import {createRef, waitFor} from '@motion-canvas/core';
export default makeScene2D(function* (view) {
  view.fill('#15283F');
  view.add(<Line points={[[-140,35],[125,35]]} stroke={'#F5E9CA'} lineWidth={5}/>);
  const signal=createRef<Rect>(); const receiver=createRef<Circle>();
  view.add(<Rect ref={signal} x={-25} y={20} width={20} height={20} fill={'#F3AE35'}/>);
  view.add(<Circle ref={receiver} x={125} y={20} width={30} height={30} fill={'#F5E9CA'}/>);
  yield* signal().x(125,.9);
  yield* receiver().fill('#72C9B5',.2);
  yield* waitFor(1);
});
