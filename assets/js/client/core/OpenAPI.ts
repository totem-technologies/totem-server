import type { ApiRequestOptions } from "./ApiRequestOptions"

type Headers = Record
type Middleware<T> = (value: T) => T | Promise
type Resolver<T> = (options: ApiRequestOptions) => Promise

export class Interceptors<T> {
  _fns: Middleware[]

  constructor() {
    this._fns = []
  }

  eject(fn: Middleware): void {
    const index = this._fns.indexOf(fn)
    if (index !== -1) {
      this._fns = [...this._fns.slice(0, index), ...this._fns.slice(index + 1)]
    }
  }

  use(fn: Middleware): void {
    this._fns = [...this._fns, fn]
  }
}

export type OpenAPIConfig = {
  BASE: string
  CREDENTIALS: "include" | "omit" | "same-origin"
  ENCODE_PATH?: ((path: string) => string) | undefined
  HEADERS?: Headers | Resolver | undefined
  PASSWORD?: string | Resolver | undefined
  TOKEN?: string | Resolver | undefined
  USERNAME?: string | Resolver | undefined
  VERSION: string
  WITH_CREDENTIALS: boolean
  interceptors: {
    request: Interceptors
    response: Interceptors
  }
}

export const OpenAPI: OpenAPIConfig = {
  BASE: "",
  CREDENTIALS: "include",
  ENCODE_PATH: undefined,
  HEADERS: undefined,
  PASSWORD: undefined,
  TOKEN: undefined,
  USERNAME: undefined,
  VERSION: "1",
  WITH_CREDENTIALS: false,
  interceptors: {
    request: new Interceptors(),
    response: new Interceptors(),
  },
}
