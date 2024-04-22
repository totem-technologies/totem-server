class UserSchema {
  private _email: string
  private _reservedName?: string | null
  private _isStaff?: boolean
  private _isActive?: boolean
  private _isSuperuser?: boolean
  private _additionalProperties?: Map<string, any>

  constructor(input: {
    email: string
    reservedName?: string | null
    isStaff?: boolean
    isActive?: boolean
    isSuperuser?: boolean
    additionalProperties?: Map<string, any>
  }) {
    this._email = input.email
    this._reservedName = input.reservedName
    this._isStaff = input.isStaff
    this._isActive = input.isActive
    this._isSuperuser = input.isSuperuser
    this._additionalProperties = input.additionalProperties
  }

  get email(): string {
    return this._email
  }
  set email(email: string) {
    this._email = email
  }

  get reservedName(): string | null | undefined {
    return this._reservedName
  }
  set reservedName(reservedName: string | null | undefined) {
    this._reservedName = reservedName
  }

  get isStaff(): boolean | undefined {
    return this._isStaff
  }
  set isStaff(isStaff: boolean | undefined) {
    this._isStaff = isStaff
  }

  get isActive(): boolean | undefined {
    return this._isActive
  }
  set isActive(isActive: boolean | undefined) {
    this._isActive = isActive
  }

  get isSuperuser(): boolean | undefined {
    return this._isSuperuser
  }
  set isSuperuser(isSuperuser: boolean | undefined) {
    this._isSuperuser = isSuperuser
  }

  get additionalProperties(): Map<string, any> | undefined {
    return this._additionalProperties
  }
  set additionalProperties(additionalProperties: Map<string, any> | undefined) {
    this._additionalProperties = additionalProperties
  }

  public marshal(): string {
    let json = "{"
    if (this.email !== undefined) {
      json += `"email": ${
        typeof this.email === "number" || typeof this.email === "boolean"
          ? this.email
          : JSON.stringify(this.email)
      },`
    }
    if (this.reservedName !== undefined) {
      json += `"name": ${
        typeof this.reservedName === "number" ||
        typeof this.reservedName === "boolean"
          ? this.reservedName
          : JSON.stringify(this.reservedName)
      },`
    }
    if (this.isStaff !== undefined) {
      json += `"is_staff": ${
        typeof this.isStaff === "number" || typeof this.isStaff === "boolean"
          ? this.isStaff
          : JSON.stringify(this.isStaff)
      },`
    }
    if (this.isActive !== undefined) {
      json += `"is_active": ${
        typeof this.isActive === "number" || typeof this.isActive === "boolean"
          ? this.isActive
          : JSON.stringify(this.isActive)
      },`
    }
    if (this.isSuperuser !== undefined) {
      json += `"is_superuser": ${
        typeof this.isSuperuser === "number" ||
        typeof this.isSuperuser === "boolean"
          ? this.isSuperuser
          : JSON.stringify(this.isSuperuser)
      },`
    }
    if (this.additionalProperties !== undefined) {
      for (const [key, value] of this.additionalProperties.entries()) {
        //Only unwrap those that are not already a property in the JSON object
        if (
          [
            "email",
            "name",
            "is_staff",
            "is_active",
            "is_superuser",
            "additionalProperties",
          ].includes(String(key))
        )
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

  public static unmarshal(json: string | object): UserSchema {
    const obj = typeof json === "object" ? json : JSON.parse(json)
    const instance = new UserSchema({} as any)

    if (obj["email"] !== undefined) {
      instance.email = obj["email"]
    }
    if (obj["name"] !== undefined) {
      instance.reservedName = obj["name"]
    }
    if (obj["is_staff"] !== undefined) {
      instance.isStaff = obj["is_staff"]
    }
    if (obj["is_active"] !== undefined) {
      instance.isActive = obj["is_active"]
    }
    if (obj["is_superuser"] !== undefined) {
      instance.isSuperuser = obj["is_superuser"]
    }

    instance.additionalProperties = new Map()
    const propsToCheck = Object.entries(obj).filter(([key]) => {
      return ![
        "email",
        "name",
        "is_staff",
        "is_active",
        "is_superuser",
        "additionalProperties",
      ].includes(key)
    })
    for (const [key, value] of propsToCheck) {
      instance.additionalProperties.set(key, value as any)
    }
    return instance
  }
}
export default UserSchema
