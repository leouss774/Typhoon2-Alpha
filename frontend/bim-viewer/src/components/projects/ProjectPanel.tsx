import { Component, Vue } from "vue-property-decorator";
import { VNode } from "vue/types/umd";
import styles from "./projectPanel.module.scss";
import Viewer3DContainer from "../viewer-container/Viewer3DContainer";

export interface ProjectPanelProps {
}

@Component
export default class ProjectPanel extends Vue {
  projectId?: string;

  mounted() {
  }

  /**
   * URL du modèle à charger automatiquement, passée en query param
   * `?model=<url>` (Typhon : /bim-viewer/projects/remote?model=...).
   * Le projectId "remote" n'existe pas dans config/projects.json : quand
   * ce param est présent, Viewer3DContainer construit un projet synthétique
   * à partir de l'URL au lieu de chercher dans les projets d'exemple.
   */
  get modelUrl(): string {
    const model = this.$router.currentRoute.query.model;
    return typeof model === "string" ? model : "";
  }

  getProjectId() {
    this.projectId = this.$router.currentRoute.params.projectId;
    if (!this.projectId) {
      console.error("[PP] Invalid projectId!");
      return;
    }
    return this.projectId;
  }

  protected render(): VNode {
    return (
      <div ref="projectPanel" class={styles.projectPanel}>
        <Viewer3DContainer projectId={this.getProjectId()} modelUrl={this.modelUrl}></Viewer3DContainer>
      </div>
    );
  }
}
