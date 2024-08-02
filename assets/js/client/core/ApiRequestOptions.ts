export type ApiRequestOptions<T = unknown> = {
  readonly body?: any
  readonly cookies?: Record
  readonly errors?: Record
  readonly formData?: Record | any[] | Blob | File
  readonly headers?: Record
  readonly mediaType?: string
  readonly method:
    | "DELETE"
    | "GET"
    | "HEAD"
    | "OPTIONS"
    | "PATCH"
    | "POST"
    | "PUT"
  readonly path?: Record
  readonly query?: Record
  readonly responseHeader?: string
  readonly responseTransformer?: (data: unknown) => Promise
  readonly url: string
}
