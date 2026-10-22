export interface Shape {
  area(): number;
}

export abstract class Base implements Shape {
  abstract area(): number;

  describe(): string {
    return `area=${this.area()}`;
  }
}

export class Circle extends Base {
  constructor(private radius: number) {
    super();
  }

  area(): number {
    return Math.PI * this.radius * this.radius;
  }
}

export class Ring extends Circle {}

export enum Color {
  Red,
  Green,
}

function orphan(): void {}
