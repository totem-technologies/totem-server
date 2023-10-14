import { useEffect, useState } from "preact/hooks"

function FeaturedLinks(props) {
  if (!props.links) return <></>
  return (
    <>
      {props.links.map((link) => (
        <a class="pr-5 hover:text-tblue" href={link.href}>
          {link.title}
        </a>
      ))}
    </>
  )
}

function MenuIcon(props) {
  return (
    <svg
      class="cursor-pointer text-gray-500 md:hidden"
      width="17"
      height="17"
      viewBox="0 0 24 24"
      xmlns="http://www.w3.org/2000/svg"
    >
      <g fill="none">
        <path d="M24 0v24H0V0h24ZM12.593 23.258l-.011.002l-.071.035l-.02.004l-.014-.004l-.071-.035c-.01-.004-.019-.001-.024.005l-.004.01l-.017.428l.005.02l.01.013l.104.074l.015.004l.012-.004l.104-.074l.012-.016l.004-.017l-.017-.427c-.002-.01-.009-.017-.017-.018Zm.265-.113l-.013.002l-.185.093l-.01.01l-.003.011l.018.43l.005.012l.008.007l.201.093c.012.004.023 0 .029-.008l.004-.014l-.034-.614c-.003-.012-.01-.02-.02-.022Zm-.715.002a.023.023 0 0 0-.027.006l-.006.014l-.034.614c0 .012.007.02.017.024l.015-.002l.201-.093l.01-.008l.004-.011l.017-.43l-.003-.012l-.01-.01l-.184-.092Z" />
        <path
          fill="#000000"
          d="M20 17.5a1.5 1.5 0 0 1 .144 2.993L20 20.5H4a1.5 1.5 0 0 1-.144-2.993L4 17.5h16Zm0-7a1.5 1.5 0 0 1 0 3H4a1.5 1.5 0 0 1 0-3h16Zm0-7a1.5 1.5 0 0 1 0 3H4a1.5 1.5 0 1 1 0-3h16Z"
        />
      </g>
    </svg>
  )
}

function LoggedOutMenuIcons(props) {
  return (
    <>
      <a
        class="inline py-3 pr-2 text-sm text-gray-500"
        href={props.links.login}
      >
        Login
      </a>
      <a class="btn btn-primary btn-sm" href={`${props.links.home}#signup`}>
        Start
      </a>
      <span class="drawer-content md:hidden">
        <label
          for="nav-bar-drawer"
          aria-label="open sidebar"
          class="btn btn-square btn-ghost"
        >
          <MenuIcon />
        </label>
      </span>
    </>
  )
}

function LoggedInMenuIcons(props) {
  return (
    <label
      for="nav-bar-drawer"
      aria-label="open sidebar"
      class="btn btn-square btn-ghost rounded-full"
    >
      {props.avatar}
    </label>
  )
}

function LoggedInMenu({ user, links }) {
  return (
    <>
      <ul class="menu">
        <li>
          <a class="pr-5 hover:text-tblue" href={user.home}>
            My Home
          </a>
        </li>
        {links.account.map((link) => (
          <li>
            <a
              class="pr-5 hover:text-tblue"
              href={link.href}
              target={link.target}
            >
              {link.title}
            </a>
          </li>
        ))}
        <li>
          <a class="pr-5 text-tpinkTint hover:text-error" href={links.logout}>
            Logout
          </a>
        </li>
      </ul>
    </>
  )
}

function LoggedOutMenu({ links }) {
  return (
    <>
      <ul class="menu">
        <li>
          <a class="pr-5 hover:text-tblue" href={links.home}>
            Home
          </a>
        </li>
        {links.marketing.map((link) => (
          <li>
            <a class="pr-5 hover:text-tblue" href={link.href}>
              {link.title}
            </a>
          </li>
        ))}
      </ul>
    </>
  )
}

function NavBar(props) {
  const [links, setLinks] = useState({})
  const [user, setUser] = useState({})
  const [data, setData] = useState({})
  const [loaded, setLoaded] = useState(false)
  useEffect(() => {
    const data = JSON.parse(document.getElementById(props.dataid).textContent)
    setData(data)
    setLinks(data.links)
    setUser(data.user)
    setLoaded(true)
  }, [])
  const homeLink = user.auth ? user.home : links.home
  const marketing = (
    <>
      {links.marketing &&
        links.marketing.map((link) => (
          <a class="pr-5 hover:text-tblue" href={link.href}>
            {link.title}
          </a>
        ))}
    </>
  )
  if (!loaded) {
    return <div></div>
  }

  const featuredLinks = user.auth ? [] : links.marketing

  return (
    <div class="center drawer  drawer-end mx-auto flex max-w-5xl flex-wrap items-center justify-between py-2 md:px-5 ">
      <input id="nav-bar-drawer" type="checkbox" class="drawer-toggle" />
      <a
        class="title-font items-center font-medium text-gray-900"
        href={homeLink}
      >
        <img class="hidden sm:block" src={data.logo} width="100" alt="" />
        <img class="sm:hidden" src={data.symbol} width="30" alt="" />
      </a>
      <div class="hidden pt-2 md:block">
        <FeaturedLinks links={featuredLinks} />
      </div>
      <div class="flex items-center gap-2">
        {!user.auth && <LoggedOutMenuIcons links={links} />}
        {user.auth && (
          <LoggedInMenuIcons user={user} avatar={props.avatar} links={links} />
        )}
      </div>
      <div class="drawer-side z-50">
        <label
          for="nav-bar-drawer"
          aria-label="close sidebar"
          class="drawer-overlay"
        ></label>
        <div class="min-h-full w-80 bg-tcreme p-4">
          {user.auth ? (
            <LoggedInMenu user={user} links={links} />
          ) : (
            <LoggedOutMenu links={links} />
          )}
        </div>
      </div>
    </div>
  )
}

NavBar.tagName = "t-navbar"

export default NavBar
