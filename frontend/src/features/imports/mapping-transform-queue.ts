export interface MappingTransformResult<Form> {
  mapping_source: string;
  form: Form | null;
}

/** Serializes pure server transforms without parsing or reconstructing opaque source text. */
export class MappingTransformQueue<Edit, Form> {
  #source: string;
  #tail: Promise<void> = Promise.resolve();
  #pending = 0;
  #blocked = false;

  constructor(source: string) {
    this.#source = source;
  }

  get source(): string {
    return this.#source;
  }

  get pending(): number {
    return this.#pending;
  }

  get blocked(): boolean {
    return this.#blocked;
  }

  enqueue(
    edit: Edit,
    transform: (source: string, edit: Edit) => Promise<MappingTransformResult<Form>>,
  ): Promise<MappingTransformResult<Form>> {
    this.#pending += 1;
    const request = this.#tail.then(async () => {
      if (this.#blocked) throw new Error("A previous mapping transform needs an explicit retry.");
      const result = await transform(this.#source, edit);
      this.#source = result.mapping_source;
      return result;
    });
    this.#tail = request.then(
      () => undefined,
      () => {
        this.#blocked = true;
      },
    );
    return request.finally(() => {
      this.#pending -= 1;
    });
  }

  reset(source = this.#source): void {
    if (this.#pending > 0) throw new Error("Cannot reset mapping transforms while requests are pending.");
    this.#source = source;
    this.#tail = Promise.resolve();
    this.#blocked = false;
  }
}
