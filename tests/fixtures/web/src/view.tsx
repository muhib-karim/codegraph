import { make } from './app';

export function Badge(props: { r: number }) {
  const c = make(props.r);
  return <span title="badge">{c.area()}</span>;
}
