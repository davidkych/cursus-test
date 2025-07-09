import { createRouter, createWebHistory } from 'vue-router';
import Welcome from '../components/Welcome.vue';

const routes = [
  { path: '/', name: 'Home', component: Welcome }
];

export default createRouter({
  history: createWebHistory(),
  routes
});
