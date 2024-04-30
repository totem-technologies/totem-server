// This file is auto-generated by @hey-api/openapi-ts

export const $LoginOut = {
  properties: {
    login: {
      title: "Login",
      type: "boolean",
    },
  },
  required: ["login"],
  title: "LoginOut",
  type: "object",
} as const

export const $TokenOut = {
  properties: {
    key: {
      title: "Key",
      type: "string",
    },
  },
  required: ["key"],
  title: "TokenOut",
  type: "object",
} as const

export const $ProfileAvatarTypeEnum = {
  enum: ["TD", "IM"],
  title: "ProfileAvatarTypeEnum",
  type: "string",
} as const

export const $UserSchema = {
  properties: {
    profile_avatar_type: {
      $ref: "#/components/schemas/ProfileAvatarTypeEnum",
    },
    name: {
      anyOf: [
        {
          maxLength: 255,
          type: "string",
        },
        {
          type: "null",
        },
      ],
      title: "Name",
    },
    profile_avatar_seed: {
      format: "uuid",
      title: "Profile Avatar Seed",
      type: "string",
    },
    profile_image: {
      anyOf: [
        {
          type: "string",
        },
        {
          type: "null",
        },
      ],
      description:
        "Profile image, must be under 5mb. Will be cropped to a square.",
      title: "Profile Image",
    },
  },
  required: ["profile_avatar_type"],
  title: "UserSchema",
  type: "object",
} as const

export const $Message = {
  properties: {
    message: {
      title: "Message",
      type: "string",
    },
  },
  required: ["message"],
  title: "Message",
  type: "object",
} as const

export const $EventsFilterSchema = {
  properties: {
    category: {
      anyOf: [
        {
          type: "string",
        },
        {
          type: "null",
        },
      ],
      title: "Category",
    },
    author: {
      anyOf: [
        {
          type: "string",
        },
        {
          type: "null",
        },
      ],
      title: "Author",
    },
  },
  required: ["category", "author"],
  title: "EventsFilterSchema",
  type: "object",
} as const

export const $Input = {
  properties: {
    limit: {
      default: 100,
      minimum: 1,
      title: "Limit",
      type: "integer",
    },
    offset: {
      default: 0,
      minimum: 0,
      title: "Offset",
      type: "integer",
    },
  },
  title: "Input",
  type: "object",
} as const

export const $CircleEventSchema = {
  properties: {
    circle: {
      $ref: "#/components/schemas/CircleSchema",
    },
    url: {
      title: "Url",
      type: "string",
    },
    start: {
      format: "date-time",
      title: "Start",
      type: "string",
    },
    slug: {
      title: "Slug",
      type: "string",
    },
    date_created: {
      format: "date-time",
      title: "Date Created",
      type: "string",
    },
    date_modified: {
      format: "date-time",
      title: "Date Modified",
      type: "string",
    },
  },
  required: ["circle", "url", "date_created", "date_modified"],
  title: "CircleEventSchema",
  type: "object",
} as const

export const $CircleSchema = {
  properties: {
    author: {
      $ref: "#/components/schemas/UserSchema",
    },
    title: {
      maxLength: 255,
      title: "Title",
      type: "string",
    },
    slug: {
      title: "Slug",
      type: "string",
    },
    date_created: {
      format: "date-time",
      title: "Date Created",
      type: "string",
    },
    date_modified: {
      format: "date-time",
      title: "Date Modified",
      type: "string",
    },
  },
  required: ["author", "title", "date_created", "date_modified"],
  title: "CircleSchema",
  type: "object",
} as const

export const $PagedCircleEventSchema = {
  properties: {
    items: {
      items: {
        $ref: "#/components/schemas/CircleEventSchema",
      },
      title: "Items",
      type: "array",
    },
    count: {
      title: "Count",
      type: "integer",
    },
  },
  required: ["items", "count"],
  title: "PagedCircleEventSchema",
  type: "object",
} as const

export const $AuthorFilterSchema = {
  properties: {
    name: {
      title: "Name",
      type: "string",
    },
    slug: {
      title: "Slug",
      type: "string",
    },
  },
  required: ["name", "slug"],
  title: "AuthorFilterSchema",
  type: "object",
} as const

export const $CategoryFilterSchema = {
  properties: {
    name: {
      title: "Name",
      type: "string",
    },
    slug: {
      title: "Slug",
      type: "string",
    },
  },
  required: ["name", "slug"],
  title: "CategoryFilterSchema",
  type: "object",
} as const

export const $FilterOptionsSchema = {
  properties: {
    categories: {
      items: {
        $ref: "#/components/schemas/CategoryFilterSchema",
      },
      title: "Categories",
      type: "array",
    },
    authors: {
      items: {
        $ref: "#/components/schemas/AuthorFilterSchema",
      },
      title: "Authors",
      type: "array",
    },
  },
  required: ["categories", "authors"],
  title: "FilterOptionsSchema",
  type: "object",
} as const