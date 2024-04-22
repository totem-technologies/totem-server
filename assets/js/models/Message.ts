class Message {
  private _message: string
  private _additionalProperties?: Map<string, any>

  constructor(input: {
    message: string
    additionalProperties?: Map<string, any>
  }) {
    this._message = input.message
    this._additionalProperties = input.additionalProperties
  }

  get message(): string {
    return this._message
  }
  set message(message: string) {
    this._message = message
  }

  get additionalProperties(): Map<string, any> | undefined {
    return this._additionalProperties
  }
  set additionalProperties(additionalProperties: Map<string, any> | undefined) {
    this._additionalProperties = additionalProperties
  }

  public marshal(): string {
    let json = "{"
    if (this.message !== undefined) {
      json += `"message": ${
        typeof this.message === "number" || typeof this.message === "boolean"
          ? this.message
          : JSON.stringify(this.message)
      },`
    }
    if (this.additionalProperties !== undefined) {
      for (const [key, value] of this.additionalProperties.entries()) {
        //Only unwrap those that are not already a property in the JSON object
        if (["message", "additionalProperties"].includes(String(key))) continue
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

  public static unmarshal(json: string | object): Message {
    const obj = typeof json === "object" ? json : JSON.parse(json)
    const instance = new Message({} as any)

    if (obj["message"] !== undefined) {
      instance.message = obj["message"]
    }

    instance.additionalProperties = new Map()
    const propsToCheck = Object.entries(obj).filter(([key]) => {
      return !["message", "additionalProperties"].includes(key)
    })
    for (const [key, value] of propsToCheck) {
      instance.additionalProperties.set(key, value as any)
    }
    return instance
  }
}
export default Message
