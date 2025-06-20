// This file is auto-generated by @hey-api/openapi-ts

import { type Options as ClientOptions, type TDataShape, type Client, formDataBodySerializer } from '@hey-api/client-fetch';
import type { TotemApiApiCurrentUserData, TotemApiApiCurrentUserResponses, TotemApiApiCurrentUserErrors, TotemApiApiUserAvatarUpdateData, TotemApiApiUserAvatarUpdateResponses, TotemApiApiUserAvatarUpdateErrors, TotemApiApiUserUploadProfileImageData, TotemApiApiUserUploadProfileImageResponses, TotemApiApiUserUploadProfileImageErrors, TotemCirclesApiListEventsData, TotemCirclesApiListEventsResponses, TotemCirclesApiFilterOptionsData, TotemCirclesApiFilterOptionsResponses, TotemCirclesApiEventDetailData, TotemCirclesApiEventDetailResponses, TotemCirclesApiUpcomingEventsData, TotemCirclesApiUpcomingEventsResponses, TotemCirclesApiWebflowEventsListData, TotemCirclesApiWebflowEventsListResponses, TotemCirclesApiListSpacesData, TotemCirclesApiListSpacesResponses } from './types.gen';
import { client as _heyApiClient } from './client.gen';

export type Options<TData extends TDataShape = TDataShape, ThrowOnError extends boolean = boolean> = ClientOptions<TData, ThrowOnError> & {
    /**
     * You can provide a client instance returned by `createClient()` instead of
     * individual options. This might be also useful if you want to implement a
     * custom client.
     */
    client?: Client;
    /**
     * You can pass arbitrary values through the `meta` object. This can be
     * used to access values that aren't defined as part of the SDK function.
     */
    meta?: Record<string, unknown>;
};

/**
 * Current User
 */
export const totemApiApiCurrentUser = <ThrowOnError extends boolean = false>(options?: Options<TotemApiApiCurrentUserData, ThrowOnError>) => {
    return (options?.client ?? _heyApiClient).get<TotemApiApiCurrentUserResponses, TotemApiApiCurrentUserErrors, ThrowOnError>({
        url: '/api/v1/auth/currentuser',
        ...options
    });
};

/**
 * User Avatar Update
 */
export const totemApiApiUserAvatarUpdate = <ThrowOnError extends boolean = false>(options: Options<TotemApiApiUserAvatarUpdateData, ThrowOnError>) => {
    return (options.client ?? _heyApiClient).post<TotemApiApiUserAvatarUpdateResponses, TotemApiApiUserAvatarUpdateErrors, ThrowOnError>({
        url: '/api/v1/user/avatarupdate',
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        }
    });
};

/**
 * User Upload Profile Image
 */
export const totemApiApiUserUploadProfileImage = <ThrowOnError extends boolean = false>(options: Options<TotemApiApiUserUploadProfileImageData, ThrowOnError>) => {
    return (options.client ?? _heyApiClient).post<TotemApiApiUserUploadProfileImageResponses, TotemApiApiUserUploadProfileImageErrors, ThrowOnError>({
        ...formDataBodySerializer,
        url: '/api/v1/user/avatarimage',
        ...options,
        headers: {
            'Content-Type': null,
            ...options.headers
        }
    });
};

/**
 * List Events
 */
export const totemCirclesApiListEvents = <ThrowOnError extends boolean = false>(options: Options<TotemCirclesApiListEventsData, ThrowOnError>) => {
    return (options.client ?? _heyApiClient).get<TotemCirclesApiListEventsResponses, unknown, ThrowOnError>({
        url: '/api/v1/spaces/',
        ...options
    });
};

/**
 * Filter Options
 */
export const totemCirclesApiFilterOptions = <ThrowOnError extends boolean = false>(options?: Options<TotemCirclesApiFilterOptionsData, ThrowOnError>) => {
    return (options?.client ?? _heyApiClient).get<TotemCirclesApiFilterOptionsResponses, unknown, ThrowOnError>({
        url: '/api/v1/spaces/filter-options',
        ...options
    });
};

/**
 * Event Detail
 */
export const totemCirclesApiEventDetail = <ThrowOnError extends boolean = false>(options: Options<TotemCirclesApiEventDetailData, ThrowOnError>) => {
    return (options.client ?? _heyApiClient).get<TotemCirclesApiEventDetailResponses, unknown, ThrowOnError>({
        url: '/api/v1/spaces/event/{event_slug}',
        ...options
    });
};

/**
 * Upcoming Events
 */
export const totemCirclesApiUpcomingEvents = <ThrowOnError extends boolean = false>(options?: Options<TotemCirclesApiUpcomingEventsData, ThrowOnError>) => {
    return (options?.client ?? _heyApiClient).get<TotemCirclesApiUpcomingEventsResponses, unknown, ThrowOnError>({
        url: '/api/v1/spaces/calendar',
        ...options
    });
};

/**
 * Webflow Events List
 */
export const totemCirclesApiWebflowEventsList = <ThrowOnError extends boolean = false>(options?: Options<TotemCirclesApiWebflowEventsListData, ThrowOnError>) => {
    return (options?.client ?? _heyApiClient).get<TotemCirclesApiWebflowEventsListResponses, unknown, ThrowOnError>({
        url: '/api/v1/spaces/webflow/list_events',
        ...options
    });
};

/**
 * List Spaces
 */
export const totemCirclesApiListSpaces = <ThrowOnError extends boolean = false>(options?: Options<TotemCirclesApiListSpacesData, ThrowOnError>) => {
    return (options?.client ?? _heyApiClient).get<TotemCirclesApiListSpacesResponses, unknown, ThrowOnError>({
        url: '/api/v1/spaces/list',
        ...options
    });
};