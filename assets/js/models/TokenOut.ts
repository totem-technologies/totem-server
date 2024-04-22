class TokenOut {
  private _key: string
  private _isBanaan: boolean
  private _additionalProperties?: Map<string, any>

  constructor(input: {
    key: string
    isBanaan: boolean
    additionalProperties?: Map<string, any>
  }) {
    this._key = input.key
    this._isBanaan = input.isBanaan
    this._additionalProperties = input.additionalProperties
  }

  get key(): string {
    return this._key
  }
  set key(key: string) {
    this._key = key
  }

  get isBanaan(): boolean {
    return this._isBanaan
  }
  set isBanaan(isBanaan: boolean) {
    this._isBanaan = isBanaan
  }

  get additionalProperties(): Map<string, any> | undefined {
    return this._additionalProperties
  }
  set additionalProperties(additionalProperties: Map<string, any> | undefined) {
    this._additionalProperties = additionalProperties
  }

  public marshal(): string {
    let json = "{"
    if (this.key !== undefined) {
      json += `"key": ${
        typeof this.key === "number" || typeof this.key === "boolean"
          ? this.key
          : JSON.stringify(this.key)
      },`
    }
    if (this.isBanaan !== undefined) {
      json += `"is_banaan": ${
        typeof this.isBanaan === "number" || typeof this.isBanaan === "boolean"
          ? this.isBanaan
          : JSON.stringify(this.isBanaan)
      },`
    }
    if (this.additionalProperties !== undefined) {
      for (const [key, value] of this.additionalProperties.entries()) {
        //Only unwrap those that are not already a property in the JSON object
        if (["key", "is_banaan", "additionalProperties"].includes(String(key)))
          continue
        json += `"${key}": ${
          typeof value === "number" || typeof value === "boolean"
            ? value
            : JSON.stringify(value)
        },`
      }
    }
    //Remove potential last comma
    return `${
      json.charAt(json.length - 1) === ","
        ? json.slice(0, json.length - 1)
        : json
    }}`
  }

  public static unmarshal(json: string | object): TokenOut {
    const obj = typeof json === "object" ? json : JSON.parse(json)
    const instance = new TokenOut({} as any)

    if (obj["key"] !== undefined) {
      instance.key = obj["key"]
    }
    if (obj["is_banaan"] !== undefined) {
      instance.isBanaan = obj["is_banaan"]
    }

    instance.additionalProperties = new Map()
    const propsToCheck = Object.entries(obj).filter(([key]) => {
      return !["key", "is_banaan", "additionalProperties"].includes(key)
    })
    for (const [key, value] of propsToCheck) {
      instance.additionalProperties.set(key, value as any)
    }
    return instance
  }
}
export default TokenOut
