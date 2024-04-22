class LoginOut {
  private _login: boolean
  private _additionalProperties?: Map<string, any>

  constructor(input: {
    login: boolean
    additionalProperties?: Map<string, any>
  }) {
    this._login = input.login
    this._additionalProperties = input.additionalProperties
  }

  get login(): boolean {
    return this._login
  }
  set login(login: boolean) {
    this._login = login
  }

  get additionalProperties(): Map<string, any> | undefined {
    return this._additionalProperties
  }
  set additionalProperties(additionalProperties: Map<string, any> | undefined) {
    this._additionalProperties = additionalProperties
  }

  public marshal(): string {
    let json = "{"
    if (this.login !== undefined) {
      json += `"login": ${
        typeof this.login === "number" || typeof this.login === "boolean"
          ? this.login
          : JSON.stringify(this.login)
      },`
    }
    if (this.additionalProperties !== undefined) {
      for (const [key, value] of this.additionalProperties.entries()) {
        //Only unwrap those that are not already a property in the JSON object
        if (["login", "additionalProperties"].includes(String(key))) continue
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

  public static unmarshal(json: string | object): LoginOut {
    const obj = typeof json === "object" ? json : JSON.parse(json)
    const instance = new LoginOut({} as any)

    if (obj["login"] !== undefined) {
      instance.login = obj["login"]
    }

    instance.additionalProperties = new Map()
    const propsToCheck = Object.entries(obj).filter(([key]) => {
      return !["login", "additionalProperties"].includes(key)
    })
    for (const [key, value] of propsToCheck) {
      instance.additionalProperties.set(key, value as any)
    }
    return instance
  }
}
export default LoginOut
