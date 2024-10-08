// This file is auto-generated by @hey-api/openapi-ts

export const LoginOutSchema = {
    properties: {
        login: {
            title: 'Login',
            type: 'boolean'
        }
    },
    required: ['login'],
    title: 'LoginOut',
    type: 'object'
} as const;

export const TokenOutSchema = {
    properties: {
        key: {
            title: 'Key',
            type: 'string'
        }
    },
    required: ['key'],
    title: 'TokenOut',
    type: 'object'
} as const;

export const ProfileAvatarTypeEnumSchema = {
    enum: ['TD', 'IM'],
    title: 'ProfileAvatarTypeEnum',
    type: 'string'
} as const;

export const UserSchemaSchema = {
    properties: {
        profile_avatar_type: {
            '$ref': '#/components/schemas/ProfileAvatarTypeEnum'
        },
        name: {
            anyOf: [
                {
                    maxLength: 255,
                    type: 'string'
                },
                {
                    type: 'null'
                }
            ],
            title: 'Name'
        },
        is_staff: {
            default: false,
            description: 'Designates whether the user can log into this admin site.',
            title: 'Staff Status',
            type: 'boolean'
        },
        profile_avatar_seed: {
            format: 'uuid',
            title: 'Profile Avatar Seed',
            type: 'string'
        },
        profile_image: {
            anyOf: [
                {
                    type: 'string'
                },
                {
                    type: 'null'
                }
            ],
            description: 'Profile image, must be under 5mb. Will be cropped to a square.',
            title: 'Profile Image'
        }
    },
    required: ['profile_avatar_type'],
    title: 'UserSchema',
    type: 'object'
} as const;

export const MessageSchema = {
    properties: {
        message: {
            title: 'Message',
            type: 'string'
        }
    },
    required: ['message'],
    title: 'Message',
    type: 'object'
} as const;

export const EventsFilterSchemaSchema = {
    properties: {
        category: {
            anyOf: [
                {
                    type: 'string'
                },
                {
                    type: 'null'
                }
            ],
            title: 'Category'
        },
        author: {
            anyOf: [
                {
                    type: 'string'
                },
                {
                    type: 'null'
                }
            ],
            title: 'Author'
        }
    },
    required: ['category', 'author'],
    title: 'EventsFilterSchema',
    type: 'object'
} as const;

export const InputSchema = {
    properties: {
        limit: {
            default: 100,
            minimum: 1,
            title: 'Limit',
            type: 'integer'
        },
        offset: {
            default: 0,
            minimum: 0,
            title: 'Offset',
            type: 'integer'
        }
    },
    title: 'Input',
    type: 'object'
} as const;

export const EventListSchemaSchema = {
    properties: {
        space: {
            '$ref': '#/components/schemas/SpaceSchema'
        },
        url: {
            title: 'Url',
            type: 'string'
        },
        start: {
            format: 'date-time',
            title: 'Start',
            type: 'string'
        },
        slug: {
            anyOf: [
                {
                    type: 'string'
                },
                {
                    type: 'null'
                }
            ],
            title: 'Slug'
        },
        date_created: {
            format: 'date-time',
            title: 'Date Created',
            type: 'string'
        },
        date_modified: {
            format: 'date-time',
            title: 'Date Modified',
            type: 'string'
        },
        title: {
            anyOf: [
                {
                    maxLength: 255,
                    type: 'string'
                },
                {
                    type: 'null'
                }
            ],
            title: 'Title'
        }
    },
    required: ['space', 'url', 'date_created', 'date_modified'],
    title: 'EventListSchema',
    type: 'object'
} as const;

export const PagedEventListSchemaSchema = {
    properties: {
        items: {
            items: {
                '$ref': '#/components/schemas/EventListSchema'
            },
            title: 'Items',
            type: 'array'
        },
        count: {
            title: 'Count',
            type: 'integer'
        }
    },
    required: ['items', 'count'],
    title: 'PagedEventListSchema',
    type: 'object'
} as const;

export const SpaceSchemaSchema = {
    properties: {
        author: {
            '$ref': '#/components/schemas/UserSchema'
        },
        title: {
            maxLength: 255,
            title: 'Title',
            type: 'string'
        },
        slug: {
            anyOf: [
                {
                    type: 'string'
                },
                {
                    type: 'null'
                }
            ],
            title: 'Slug'
        },
        date_created: {
            format: 'date-time',
            title: 'Date Created',
            type: 'string'
        },
        date_modified: {
            format: 'date-time',
            title: 'Date Modified',
            type: 'string'
        },
        subtitle: {
            maxLength: 2000,
            title: 'Subtitle',
            type: 'string'
        }
    },
    required: ['author', 'title', 'date_created', 'date_modified', 'subtitle'],
    title: 'SpaceSchema',
    type: 'object'
} as const;

export const AuthorFilterSchemaSchema = {
    properties: {
        name: {
            title: 'Name',
            type: 'string'
        },
        slug: {
            title: 'Slug',
            type: 'string'
        }
    },
    required: ['name', 'slug'],
    title: 'AuthorFilterSchema',
    type: 'object'
} as const;

export const CategoryFilterSchemaSchema = {
    properties: {
        name: {
            title: 'Name',
            type: 'string'
        },
        slug: {
            title: 'Slug',
            type: 'string'
        }
    },
    required: ['name', 'slug'],
    title: 'CategoryFilterSchema',
    type: 'object'
} as const;

export const FilterOptionsSchemaSchema = {
    properties: {
        categories: {
            items: {
                '$ref': '#/components/schemas/CategoryFilterSchema'
            },
            title: 'Categories',
            type: 'array'
        },
        authors: {
            items: {
                '$ref': '#/components/schemas/AuthorFilterSchema'
            },
            title: 'Authors',
            type: 'array'
        }
    },
    required: ['categories', 'authors'],
    title: 'FilterOptionsSchema',
    type: 'object'
} as const;

export const EventDetailSchemaSchema = {
    properties: {
        slug: {
            title: 'Slug',
            type: 'string'
        },
        title: {
            title: 'Title',
            type: 'string'
        },
        description: {
            title: 'Description',
            type: 'string'
        },
        price: {
            title: 'Price',
            type: 'integer'
        },
        seats_left: {
            title: 'Seats Left',
            type: 'integer'
        },
        duration: {
            title: 'Duration',
            type: 'integer'
        },
        recurring: {
            title: 'Recurring',
            type: 'string'
        },
        subscribers: {
            title: 'Subscribers',
            type: 'integer'
        },
        start: {
            format: 'date-time',
            title: 'Start',
            type: 'string'
        },
        attending: {
            title: 'Attending',
            type: 'boolean'
        },
        open: {
            title: 'Open',
            type: 'boolean'
        },
        started: {
            title: 'Started',
            type: 'boolean'
        },
        cancelled: {
            title: 'Cancelled',
            type: 'boolean'
        },
        joinable: {
            title: 'Joinable',
            type: 'boolean'
        },
        ended: {
            title: 'Ended',
            type: 'boolean'
        },
        rsvp_url: {
            title: 'Rsvp Url',
            type: 'string'
        },
        join_url: {
            anyOf: [
                {
                    type: 'string'
                },
                {
                    type: 'null'
                }
            ],
            title: 'Join Url'
        },
        subscribe_url: {
            title: 'Subscribe Url',
            type: 'string'
        },
        calLink: {
            title: 'Callink',
            type: 'string'
        },
        attendees: {
            items: {
                '$ref': '#/components/schemas/UserSchema'
            },
            title: 'Attendees',
            type: 'array'
        },
        subscribed: {
            anyOf: [
                {
                    type: 'boolean'
                },
                {
                    type: 'null'
                }
            ],
            title: 'Subscribed'
        },
        user_timezone: {
            anyOf: [
                {
                    type: 'string'
                },
                {
                    type: 'null'
                }
            ],
            title: 'User Timezone'
        }
    },
    required: ['slug', 'title', 'description', 'price', 'seats_left', 'duration', 'recurring', 'subscribers', 'start', 'attending', 'open', 'started', 'cancelled', 'joinable', 'ended', 'rsvp_url', 'join_url', 'subscribe_url', 'calLink', 'attendees', 'subscribed', 'user_timezone'],
    title: 'EventDetailSchema',
    type: 'object'
} as const;

export const EventCalendarFilterSchemaSchema = {
    properties: {
        space_slug: {
            description: 'Space slug',
            title: 'Space Slug',
            type: 'string'
        },
        month: {
            default: 10,
            description: 'Month of the year, 1-12',
            exclusiveMaximum: 13,
            exclusiveMinimum: 0,
            title: 'Month',
            type: 'integer'
        },
        year: {
            default: 2024,
            description: 'Year of the month, e.g. 2024',
            exclusiveMaximum: 3000,
            exclusiveMinimum: 1000,
            title: 'Year',
            type: 'integer'
        }
    },
    title: 'EventCalendarFilterSchema',
    type: 'object'
} as const;

export const EventCalendarSchemaSchema = {
    properties: {
        title: {
            title: 'Title',
            type: 'string'
        },
        start: {
            title: 'Start',
            type: 'string'
        },
        slug: {
            title: 'Slug',
            type: 'string'
        },
        url: {
            title: 'Url',
            type: 'string'
        }
    },
    required: ['title', 'start', 'slug', 'url'],
    title: 'EventCalendarSchema',
    type: 'object'
} as const;