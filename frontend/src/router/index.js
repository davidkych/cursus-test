import { createRouter, createWebHistory } from 'vue-router';

import Welcome      from '../components/Welcome.vue';
import Login        from '../components/Login.vue';
import AccountMain  from '../components/AccountMain.vue';

const routes = [
  { path: '/',               name: 'Home',         component: Welcome },
  { path: '/account/login',  name: 'Login',        component: Login   },
  { path: '/account/main',   name: 'AccountMain',  component: AccountMain }
];

export default createRouter({
  history: createWebHistory(),
  routes
});
