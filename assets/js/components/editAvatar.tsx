import {
  type ProfileAvatarTypeEnum,
  type UserSchema,
  totemApiApiCurrentUser,
  totemApiApiUserAvatarUpdate,
  totemApiApiUserUploadProfileImage,
} from "@/client"
import { createQuery } from "@tanstack/solid-query"
import { For, Show, Suspense, createEffect, createSignal } from "solid-js"
import Avatar from "./avatar"
const defaults = {}

function EditAvatar() {
  let modalRef: HTMLDialogElement | undefined
  const query = createQuery(() => ({
    queryKey: ["userData"],
    queryFn: async () => {
      const response = await totemApiApiCurrentUser()
      if (response.error) {
        throw new Error(response.error.message)
      }
      return response.data
    },
    throwOnError: true,
  }))
  const user = () => query.data
  function closeModal() {
    modalRef?.close()
  }
  return (
    <div
      onClick={() => modalRef?.showModal()}
      onKeyDown={() => modalRef?.showModal()}
      class="relative h-[150px] w-[150px] rounded-full p-1 transition hover:shadow-md">
      <Suspense fallback={"Loading..."}>
        <Avatar
          seed={user()?.profile_avatar_seed}
          size={200}
          name={user()?.name ?? ""}
          url={user()?.profile_image || ""}
          type={user()?.profile_avatar_type}
        />
        <div class="absolute bottom-2 right-2 rounded-full bg-white p-1">
          {/* biome-ignore lint/a11y/noSvgWithoutTitle: <explanation> */}
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            xmlns="http://www.w3.org/2000/svg">
            <path
              fill="#000000"
              d="m19.3 8.925l-4.25-4.2l1.4-1.4q.575-.575 1.413-.575t1.412.575l1.4 1.4q.575.575.6 1.388t-.55 1.387L19.3 8.925ZM17.85 10.4L7.25 21H3v-4.25l10.6-10.6l4.25 4.25Z"
            />
          </svg>
        </div>
        <dialog ref={modalRef} id="attending_modal" class="modal">
          <Show when={query.isSuccess} fallback={"Loading..."}>
            <EditAvatarModal
              //biome-ignore lint/style/noNonNullAssertion: <explanation>
              user={user()!}
              closeModal={closeModal}
              refetch={() => {
                query.refetch()
              }}
            />
          </Show>
        </dialog>
      </Suspense>
    </div>
  )
}

async function setUpdate(
  avatarType: ProfileAvatarTypeEnum | null,
  updateSeed: boolean
) {
  await totemApiApiUserAvatarUpdate({
    body: {
      avatar_type: avatarType,
      update_avatar_seed: updateSeed,
    },
  })
}

function openFileDialog() {
  return new Promise<File | null>((resolve) => {
    const input = document.createElement("input")
    input.type = "file"
    input.accept = "image/*"
    input.onchange = () => {
      resolve(input.files?.[0] ?? null)
    }
    input.click()
  })
}

async function getFile() {
  const file = await openFileDialog()
  if (!file) {
    throw new Error("No file selected")
  }
  return file
}

async function uploadProfileImage() {
  // propmpt user to select a file and upload it
  const file = await getFile()
  await totemApiApiUserUploadProfileImage({
    body: {
      file,
    },
  })
}

function EditAvatarModal(props: {
  user: UserSchema
  closeModal: () => void
  refetch: () => void
}) {
  const [avatarType, setAvatarType] = createSignal<ProfileAvatarTypeEnum>(
    props.user.profile_avatar_type
  )
  const [error, setError] = createSignal<string | null>(null)
  createEffect(async () => {
    try {
      await setUpdate(avatarType(), false)
      props.refetch()
    } catch (error) {
      setError(error as string)
    }
  })
  async function clickHandler() {
    if (avatarType() === "TD") {
      await setUpdate(null, true)
    }
    if (avatarType() === "IM") {
      await uploadProfileImage()
    }
    props.refetch()
  }
  return (
    <div class="modal-box flex w-96 flex-col items-center justify-center">
      <Show when={error()}>
        <div class="alert alert-error">
          <div class="flex-1">
            <p class="font-bold">Error:</p>
            <p>{error()}</p>
          </div>
        </div>
      </Show>
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: <explanation> */}
      <div
        class="relative mb-5 inline-block cursor-pointer"
        onClick={clickHandler}>
        <Avatar
          seed={props.user.profile_avatar_seed}
          size={200}
          name={props.user.name ?? ""}
          url={props.user.profile_image || ""}
          type={avatarType()}
        />
        <div class="absolute left-0 top-0 h-full w-full rounded-full bg-tcreme bg-opacity-70 opacity-0 transition-opacity hover:opacity-100">
          <h3 class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 transform">
            <Show when={avatarType() === "IM"}>Upload</Show>
            <Show when={avatarType() === "TD"}>Randomize</Show>
          </h3>
        </div>
        <div class="absolute bottom-2 right-2 rounded-full bg-white p-1">
          <Show when={avatarType() === "IM"}>
            <UploadIcon />
          </Show>
          <Show when={avatarType() === "TD"}>
            <RandomizeIcon />
          </Show>
        </div>
      </div>
      <div class="join">
        <For each={["TD", "IM"]}>
          {(e) => (
            <input
              class="btn join-item btn-sm"
              type="radio"
              name="options"
              value={e}
              checked={avatarType() === e}
              onClick={() => {
                setAvatarType(e as ProfileAvatarTypeEnum)
              }}
              aria-label={e === "TD" ? "Tie Dye" : "Image"}
            />
          )}
        </For>
      </div>
      <div class="flex gap-4 text-center">
        <button
          class="btn btn-sm mt-5"
          type="button"
          onClick={() => {
            globalThis.location.reload()
          }}>
          Close
        </button>
      </div>
    </div>
  )
}

function UploadIcon() {
  return (
    <svg
      width="25"
      class="absolute bottom-2 right-2 rounded-full bg-white p-1"
      height="25"
      viewBox="0 0 24 24"
      xmlns="http://www.w3.org/2000/svg"
      aria-labelledby="uploadIconTitle">
      <title id="uploadIconTitle">Upload Icon</title>
      <path
        fill="#000000"
        d="M11 16V7.85l-2.6 2.6L7 9l5-5l5 5l-1.4 1.45l-2.6-2.6V16h-2Zm-5 4q-.825 0-1.413-.588T4 18v-3h2v3h12v-3h2v3q0 .825-.588 1.413T18 20H6Z"
      />
    </svg>
  )
}

function RandomizeIcon() {
  return (
    <svg
      width="25"
      class="absolute bottom-2 right-2 rounded-full bg-tcreme p-1"
      height="25"
      viewBox="0 0 512 512"
      aria-labelledby="randomizeIconTitle"
      xmlns="http://www.w3.org/2000/svg">
      <title id="randomizeIconTitle">Randomize Icon</title>
      <path
        fill="#000000"
        d="M341.3 28.3v85.3H128c-70.7 0-128 57.3-128 128c0 21.5 5.8 41.4 15.2 59.2L68 263.2c-2.4-6.8-4-13.9-4-21.5c0-35.4 28.7-64 64-64h213.3V263L512 156.3V135L341.3 28.3zM444 262.8c2.4 6.8 4 13.9 4 21.5c0 35.4-28.6 64-64 64H170.7V263L0 369.7V391l170.7 106.7v-85.3H384c70.7 0 128-57.3 128-128c0-21.5-5.8-41.4-15.2-59.2L444 262.8z"
      />
    </svg>
  )
}

EditAvatar.tagName = "t-edit-avatar"
EditAvatar.propsDefault = defaults
export { EditAvatar }
