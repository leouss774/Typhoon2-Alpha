import Projects from "@/views/projects/Projects";
import ProjectPanel from "@/components/projects/ProjectPanel";
import Vue from "vue";
import VueRouter, { RouteConfig } from "vue-router";

Vue.use(VueRouter);

const routes: Array<RouteConfig> = [
  {
    path: "/projects",
    name: "Projects",
    component: Projects
  },
  {
    path: "/projects/:projectId",
    name: "ProjectPanel",
    component: ProjectPanel
  },
  {
    path: "/",
    name: "Index",
    component: Projects
  }
];

// Typhon : le viewer est servi sous /bim-viewer/ (build statique servi par
// Vite). Le mode hash par defaut (URL "#/") ne lit pas le query param
// `?model=` passe sur le chemin : on passe en mode history avec la base
// publicPath, comme ca `/bim-viewer/projects/remote?model=...` route
// directement vers le panneau de visualisation.
const router = new VueRouter({
  mode: "history",
  base: process.env.BASE_URL || "/bim-viewer/",
  routes
});

export default router;
