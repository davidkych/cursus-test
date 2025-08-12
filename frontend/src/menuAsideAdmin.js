import {
  mdiAccountCircle,
  mdiAccountPlus,
  mdiMonitor,
  mdiGithub,
  mdiLock,
  mdiAlertCircle,
  mdiSquareEditOutline,
  mdiTable,
  mdiViewList,
  mdiTelevisionGuide,
  mdiResponsive,
  mdiPalette,
  mdiReact,
} from '@mdi/js'

/**
 * Admin-mode sidebar menu
 * — every in-app route is now prefixed with /admin/*
 *   (global pages like /login, /register, /style remain unchanged)
 */
export default [
  {
    to: '/admin/dashboard',
    icon: mdiMonitor,
    label: 'Dashboard (Admin)',
  },
  {
    to: '/admin/tables',
    label: 'Tables',
    icon: mdiTable,
  },
  {
    to: '/admin/forms',
    label: 'Forms',
    icon: mdiSquareEditOutline,
  },
  {
    to: '/admin/ui',
    label: 'UI',
    icon: mdiTelevisionGuide,
  },
  {
    to: '/admin/responsive',
    label: 'Responsive',
    icon: mdiResponsive,
  },
  // ⟨NEW⟩ Codes generator
  {
    to: '/admin/codes',
    label: 'Codes',
    icon: mdiViewList,
  },
  {
    to: '/style',              // style selector (top-level guest route)
    label: 'Styles',
    icon: mdiPalette,
  },
  {
    to: '/admin/profile',
    label: 'Profile',
    icon: mdiAccountCircle,
  },
  {
    to: '/register',           // top-level guest routes (unchanged)
    label: 'Register',
    icon: mdiAccountPlus,
  },
  {
    to: '/login',
    label: 'Login',
    icon: mdiLock,
  },
  {
    to: '/error',
    label: 'Error',
    icon: mdiAlertCircle,
  },
  {
    label: 'Dropdown',
    icon: mdiViewList,
    menu: [
      { label: 'Item One' },
      { label: 'Item Two' },
    ],
  },
]
