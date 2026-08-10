import * as THREE from "three";
import * as dat from "dat.gui";
import { BooleanMessageData, MessageId } from "../postmate/Message";
import { MeasureMode } from "../measure/Measure";
import { PostmateManager } from "../postmate/PostmateManager";
import Exploder from "../exploder/Exploder";
import GroundUtils from "../utils/GroundUtils";
import SceneUtils from "../utils/SceneUtils";
import SkyboxUtils from "../utils/SkyboxUtils";
import store, { Types } from "@/store/index";
import Viewer3D from "../Viewer3D";
import Viewer3DUtils from "../utils/Viewer3DUtils";
const screenfull = require("screenfull");

export default class DatGuiHelper {
  viewer: Viewer3D | undefined;
  gui?: dat.GUI;
  exploderDict?: { [objId: number]: Exploder } = {};
  readonly postmate = PostmateManager.instance();

  /**
   *
   * @param viewer pass in the Viewer3D, so we can reference its data members
   */
  constructor(viewer: Viewer3D) {
    this.viewer = viewer;
    this.init();
    this.initPostmate();
    // Réflète dans dat.gui les niveaux auto-dérivés du rapport typhon.
    if (viewer.simulations) {
      viewer.simulations.onStateChange = (kind: string) => this.syncSimController(kind);
    }
  }

  /**
   * Met à jour les contrôles dat.gui quand le rapport impose un niveau.
   * GUARD : dat.gui `setValue()` déclenche les callbacks onChange — sans ce
   * verrou, manager → dat.gui → manager boucle à l'infini (RangeError).
   */
  private syncingSims = false;

  private syncSimController(kind: string) {
    this.syncingSims = true;
    try {
      const sim = this.viewer && this.viewer.simulations;
      if (!sim || !sim.state) {
        return;
      }
      const st = sim.state[kind as keyof typeof sim.state];
      if (!st) {
        return;
      }
      const enableCtrl = this.simEnableControllers[kind];
      const levelCtrl = this.simLevelControllers[kind];
      if (enableCtrl) {
        enableCtrl.setValue(st.enabled);
      }
      if (levelCtrl) {
        levelCtrl.setValue(st.level);
      }
    } finally {
      this.syncingSims = false;
    }
  }

  /**
   * Defined all controls here, which will be displyed in dat.GUI
   * Color should follow these formats:
   * '#ffffff', [0, 0, 0], [0, 0, 0, 0.5], { h: 100, s: 0.9, v: 0.3 }
   */
  readonly controls = {
    // Common settings
    showGroundGrid: false,
    // Typhoon : herbe + ciel nuageux actifs par défaut, pour que le bâtiment
    // soit posé sur un sol étendu plutôt que flottant sur fond dégradé.
    showGrassGround: true,
    skyMode: ["None", "Gradient ramp", "Cloudy"],
    homeView: () => console.log("[DGH] Go to home view"),
    views: ["Top", "Bottom", "Front", "Back", "Left", "Right"],
    OrthographicCamera: false,
    // viewpoints: false,
    // annotations: false,
    takeSnapshot: () => console.log("[DGH] Taking snapshot..."),
    fullScreen: () => console.log("[DGH] Full screen..."),
    webcam: false,
    uploadFile: () => console.log("[DGH] Upload file..."),

    // model operations
    // showLayerManager: false,
    showBimTree: false,
    // showPropertyPanel: false,
    transparentMode: false,
    // explodeMode: ['No explode', 'Explode', 'Explode Up'], // hide it beause it doesn't work well yet!
    sectionMode: ["No section", "Box section", "Plane section"],
    measure: ["No measure", "Distance", "Area", "Angle"],

    // Simulations (catastrophes naturelles — intensités dérivées du rapport
    // typhon, ou réglées à la main sur les projets d'exemple)
    simFlood: false,
    simFloodLevel: "modere",
    simFire: false,
    simFireLevel: "modere",
    simSeismic: false,
    simSeismicLevel: "modere",
    simSpeed: 1,
    simReset: () => console.log("[DGH] Reset simulations"),
    // filterFloor: ['No filter', '-2F', '-1F', '1F', '2F', '3F', '4F', '5F', '6F', '7F', '8F', '9F', '10F', '11F', '12F', '13F', '14F', '15F', '16F', '17F', '18F', '19F', '20F'],

    // Ambient Light (环境光)
    alVisible: true,
    alColor: "#cccccc",
    alIntensity: 1,
    alCastShadow: true, // 开启阴影

    // Directinal Light (平行光)
    dlVisible: true,
    dlColor: "#dddddd",
    dlIntensity: 2,
    dlCastShadow: true,

    // Hemisphere Light (半球光源)
    hlVisible: true,
    hlIntensity: 1,
    hlColor: [255, 255, 255, 0.6], // sky color
    hlGroundColor: [200, 255, 200, 0.6],

    // Fog
    fogEnabled: false,
    fogColor: 0xdddddd,
    fogNearDistance: 1,
    fogFarDistance: 1000,

    // Composer
    composerEnabled: false,
    renderPassEnabled: false,
    fxaaEnabled: false,
    saoEnabled: false,
    ssaoEnabled: false,
    outlineEnabled: false,
    ssaaEnabled: false,
    bloomEnabled: false,
    unrealBloomEnabled: false
  };

  /**
   * Init dat.GUI
   */
  init() {
    if (!this.viewer || !this.viewer.renderer || !this.viewer.scene) {
      throw new Error("Need to initialize renderer, scene first!");
    }
    const viewer = this.viewer; // the name doesn't good, but I cannot find a better one!
    const scene = this.viewer.scene;
    const controls = this.controls;
    this.gui = new dat.GUI({ name: "controls", autoPlace: true, width: 300, closed: true });
    // uncomment it if we want to save values into localStorage
    // gui.remember(controls)
    // this.gui.close() // collapse the panel by default
    this.gui.domElement.style.opacity = "0.6";

    // Common settings
    const sf = this.gui.addFolder("Common settings");
    sf.add(controls, "showGroundGrid").name("Show ground grid").onChange((e: boolean) => {
      if (viewer.groundGrid) {
        viewer.groundGrid.visible = e;
      } else if (e) {
        viewer.groundGrid = GroundUtils.createGroundGrid();
        scene.add(viewer.groundGrid);
        viewer.enableRender();
      }
      viewer.enableRender();
    });
    sf.add(controls, "showGrassGround").name("Show grass ground").onChange((e: boolean) => {
      if (viewer.grassGround) {
        viewer.grassGround.visible = e;
      } else if (e) {
        (async() => {
          viewer.grassGround = await GroundUtils.createGrassGround();
          scene.add(viewer.grassGround);
          viewer.enableRender();
        })();
      }
      viewer.enableRender();
    });
    const skyModeController = sf.add(controls, "skyMode", controls.skyMode).name("Sky mode");
    skyModeController.onChange((e: string) => {
      if (viewer.skyOfGradientRamp) {
        viewer.skyOfGradientRamp.visible = (e === "Gradient ramp");
      }
      if (e === "Gradient ramp") {
        if (!viewer.skyOfGradientRamp) {
          viewer.skyOfGradientRamp = SkyboxUtils.createSkyOfGradientRamp();
          scene.add(viewer.skyOfGradientRamp);
        }
        viewer.skyOfGradientRamp.visible = true;
      } else if (e === "Cloudy") {
        SkyboxUtils.createSkyFromTextures("cloudy").then(texture => {
          scene.background = texture;
        });
      } else {
        scene.background = viewer.sceneBackgroundColor;
      }
      viewer.enableRender();
    });
    skyModeController.setValue("Cloudy");
    sf.add(controls, "homeView").name("Go to home view").onChange(() => {
      viewer.goToHomeView();
    });
    sf.add(controls, "views", controls.views).name("Views").onChange((e: string) => {
      const eye = new THREE.Vector3();
      const look = new THREE.Vector3();
      Viewer3DUtils.getCameraPositionByView(scene, e, eye, look);
      viewer.flyTo(eye, look);
    });
    // const viewpointsController = sf.add(controls, "viewpoints", controls.viewpoints).name("Viewpoints");
    // viewpointsController.onChange((e: boolean) => {
    //   store.commit(Types.MUTATION_SHOW_VIEWPOINTS, e);
    // });
    // // when panel is closed/opened itself, update DatGui here
    // store.watch(
    //   (state, getters) => getters.getShowViewpoints,
    //   (visible: boolean) => {
    //     viewpointsController.setValue(visible);
    //   }
    // );
    sf.add(controls, "OrthographicCamera").name("Orth Camera").onChange((e: boolean) => {
      viewer.setToOrthographicCamera(e);
    });
    // const annotationsController = sf.add(controls, "annotations", controls.annotations).name("Annotations");
    // annotationsController.onChange((e: boolean) => {
    //   store.commit(Types.MUTATION_SHOW_ANNOTATIONS, e);
    // });
    // // when panel is closed/opened itself, update DatGui here
    // store.watch(
    //   (state, getters) => getters.getShowAnnotations,
    //   (visible: boolean) => {
    //     annotationsController.setValue(visible);
    //   }
    // );
    sf.add(controls, "takeSnapshot").name("Take snapshot").onChange(() => {
      store.commit(Types.MUTATION_SHOW_SNAPSHOT_PANEL, true);
    });
    sf.add(controls, "fullScreen").name("Full screen").onChange(() => {
      if (screenfull && screenfull.isEnabled) {
        screenfull.request();
      }
      viewer.enableRender();
    });
    // Since it is a demo, turn it off for now
    // sf.add(controls, 'webcam', controls.webcam).name('Turn on WebCam').onChange((e: boolean) => {
    //   e ? viewer.enableWebCam() : viewer.disableWebCam()
    // })
    sf.add(controls, "uploadFile").name("Upload file").onChange(() => {
      (document as any).getElementById("uploadModelFile").click();
    });

    // Model operations
    const mf = this.gui.addFolder("Model operations");
    // const showLayerManagerController = mf.add(controls, 'showLayerManager', controls.showLayerManager).name('Layer Manager')
    // showLayerManagerController.onChange((e: boolean) => {
    //   store.commit(Types.MUTATION_SHOW_LAYER_MANAGER, e)
    // })
    // // when panel is closed/opened itself, update DatGui here
    // store.watch(
    //   (state, getters) => getters.getShowLayerManager,
    //   (visible: boolean) => {
    //     showLayerManagerController.setValue(visible)
    //   }
    // )
    const showBimTreeController = mf.add(controls, "showBimTree", controls.showBimTree).name("Show BimTree");
    showBimTreeController.onChange((e: boolean) => {
      store.commit(Types.MUTATION_SHOW_BIM_TREE, e);
    });
    // when panel is closed/opened itself, update DatGui here
    store.watch(
      (state, getters) => getters.getShowBimTree,
      (visible: boolean) => {
        showBimTreeController.setValue(visible);
      }
    );
    // const showPropertyPanel = mf.add(controls, "showPropertyPanel", controls.showPropertyPanel).name("Show Property Panel");
    // showPropertyPanel.onChange((e: boolean) => {
    //   store.commit(Types.MUTATION_SHOW_PROPERTY_PANEL, e);
    // });
    // // when panel is closed/opened itself, update DatGui here
    // store.watch(
    //   (state, getters) => getters.getShowPropertyPanel,
    //   (visible: boolean) => {
    //     showPropertyPanel.setValue(visible);
    //   }
    // );
    mf.add(controls, "transparentMode", controls.transparentMode).name("Transparent mode").onChange((e: boolean) => {
      viewer.addOrRemoveObjectOpacity(e);
      viewer.enableRender();
    });
    // mf.add(controls, 'explodeMode', controls.explodeMode).name('Explode mode').onChange((e: string) => {
    //   if (e === 'No explode') {
    //     this.setExplodeMode(false)
    //   } else if (e === 'Explode') {
    //     this.setExplodeMode(true)
    //   } else if (e === 'Explode Up') {
    //     this.setExplodeMode(true, true)
    //   }
    //   viewer.enableRender()
    // })
    mf.add(controls, "sectionMode", controls.sectionMode).name("Section mode").onChange((e: string) => {
      if (e === "No section") {
        viewer.disableSection();
      } else if (e === "Box section") {
        viewer.enableSection("ObjectsBoxSection");
      } else if (e === "Plane section") {
        viewer.enableSection("PlaneSection");
      }
      viewer.enableRender();
    });
    mf.add(controls, "measure", controls.measure).name("Measure").onChange((e: string) => {
      if (!viewer.renderer) {
        return;
      }
      if (e === "No measure") {
        viewer.disableMeasure();
      } else if (e === "Distance") {
        viewer.enableMeasure(MeasureMode.Distance);
      } else if (e === "Area") {
        viewer.enableMeasure(MeasureMode.Area);
      } else if (e === "Angle") {
        viewer.enableMeasure(MeasureMode.Angle);
      }
      viewer.enableRender();
    });

    // ─── Simulations (inondation / feu / séisme) ───
    // Intensités dérivées de `aleas[*].niveau` du rapport quand il est
    // transmis (postMessage typhon:sim) ; sinon réglage manuel (projets
    // d'exemple). Avertissement pédagogique dans l'UI parente.
    const sim = viewer.simulations;
    const levelOptions: { [label: string]: string } = {
      "Très faible": "tres_faible",
      Faible: "faible",
      Modéré: "modere",
      Élevé: "eleve",
      Critique: "critique"
    };
    const simf = this.gui.addFolder("Simulations");
    this.simFolder = simf;
    this.simEnableControllers.flood = simf.add(controls, "simFlood", controls.simFlood).name("Inondation").onChange((e: boolean) => {
      if (this.syncingSims) return;
      sim && sim.setEnabled("flood", e);
      viewer.enableRender();
    });
    this.simLevelControllers.flood = simf.add(controls, "simFloodLevel", levelOptions).name("Niveau eau").onChange((e: string) => {
      if (this.syncingSims) return;
      sim && sim.setLevel("flood", e as any);
      viewer.enableRender();
    });
    this.simEnableControllers.fire = simf.add(controls, "simFire", controls.simFire).name("Feu").onChange((e: boolean) => {
      if (this.syncingSims) return;
      sim && sim.setEnabled("fire", e);
      viewer.enableRender();
    });
    this.simLevelControllers.fire = simf.add(controls, "simFireLevel", levelOptions).name("Intensité feu").onChange((e: string) => {
      if (this.syncingSims) return;
      sim && sim.setLevel("fire", e as any);
      viewer.enableRender();
    });
    this.simEnableControllers.seismic = simf.add(controls, "simSeismic", controls.simSeismic).name("Séisme").onChange((e: boolean) => {
      if (this.syncingSims) return;
      sim && sim.setEnabled("seismic", e);
      viewer.enableRender();
    });
    this.simLevelControllers.seismic = simf.add(controls, "simSeismicLevel", levelOptions).name("Intensité sismique").onChange((e: string) => {
      if (this.syncingSims) return;
      sim && sim.setLevel("seismic", e as any);
      viewer.enableRender();
    });
    simf.add(controls, "simSpeed", 0.2, 3).name("Vitesse temps réel").onChange((e: number) => {
      sim && sim.setSpeed("flood", e);
      sim && sim.setSpeed("fire", e);
      sim && sim.setSpeed("seismic", e);
      viewer.enableRender();
    });
    simf.add(controls, "simReset").name("Réarmer les simulations").onChange(() => {
      sim && sim.reset();
      viewer.enableRender();
    });
    // mf.add(controls, 'filterFloor', controls.filterFloor).name('Filter by floor').onChange((e: string) => {
    //   if (e === 'No filter') {
    //     e = '' // pass in nothing, so it clears the filter
    //   }
    //   this.filterFloor(e)
    //   viewer.enableRender()
    // })

    // Ambient light
    const al = this.viewer.ambientLight;
    const alf = this.gui.addFolder("Ambient light");
    alf.add(controls, "alVisible", controls.alVisible).name("visible").onChange((e: boolean) => {
      // assume the light is added to scene already
      al && (al.visible = e);
      viewer.enableRender();
    });
    alf.addColor(controls, "alColor").name("color").onChange((e: string) => {
      al && (al.color = new THREE.Color(e));
      viewer.enableRender();
    });
    alf.add(controls, "alIntensity", 0, 5).name("intensity").onChange((e: number) => {
      al && (al.intensity = e);
      viewer.enableRender();
    });
    alf.add(controls, "alCastShadow").name("castShadow").onChange((e: boolean) => {
      al && (al.castShadow = e);
      viewer.enableRender();
    });

    // Directional light
    const dl = this.viewer.directionalLight;
    const dlf = this.gui.addFolder("Directional light");
    dlf.add(controls, "dlVisible", controls.dlVisible).name("visible").onChange((e: boolean) => {
      // assume the light is added to scene already
      dl && (dl.visible = e);
      viewer.enableRender();
    });
    dlf.addColor(controls, "dlColor").name("color").onChange((e: string) => {
      dl && (dl.color = new THREE.Color(e));
      viewer.enableRender();
    });
    dlf.add(controls, "dlIntensity", 0, 5).name("intensity").onChange((e: number) => {
      dl && (dl.intensity = e);
      viewer.enableRender();
    });
    dlf.add(controls, "dlCastShadow").name("castShadow").onChange((e: boolean) => {
      dl && (dl.castShadow = e);
      viewer.enableRender();
    });

    // Hemisphere Light
    const hl = this.viewer.hemisphereLight;
    const hlf = this.gui.addFolder("Hemisphere Light");
    hlf.add(controls, "hlVisible", controls.hlVisible).name("visible").onChange((e: boolean) => {
      // assume the light is added to scene already
      hl && (hl.visible = e);
      viewer.enableRender();
    });
    hlf.add(controls, "hlIntensity", 0, 5).name("intensity").onChange((e: number) => {
      hl && (hl.intensity = e);
      viewer.enableRender();
    });
    hlf.addColor(controls, "hlColor").name("color").onChange((e: string) => {
      hl && (hl.color = new THREE.Color(e));
      viewer.enableRender();
    });
    hlf.addColor(controls, "hlGroundColor").name("groundColor").onChange((e: string) => {
      hl && (hl.groundColor = new THREE.Color(e));
      viewer.enableRender();
    });

    // Fog
    const ff = this.gui.addFolder("Fog");
    ff.add(controls, "fogEnabled", controls.fogEnabled).name("Enabled").onChange((e: boolean) => {
      if (e) {
        scene.fog = new THREE.Fog(controls.fogColor, controls.fogNearDistance, controls.fogFarDistance);
      } else {
        scene.fog = null;
      }
      viewer.enableRender();
    });
    ff.add(controls, "fogNearDistance", 0, 100).name("Near").onChange((e: number) => {
      controls.fogEnabled && scene && (scene.fog = new THREE.Fog(controls.fogColor, e, controls.fogFarDistance));
      viewer.enableRender();
    });
    ff.add(controls, "fogFarDistance", 100, 2000).name("Far").onChange((e: number) => {
      controls.fogEnabled && scene && (scene.fog = new THREE.Fog(controls.fogColor, controls.fogNearDistance, e));
      viewer.enableRender();
    });

    // Composer
    const cf = this.gui.addFolder("Composer");
    cf.add(controls, "composerEnabled", controls.composerEnabled).name("Composer Enabled").onChange((e: boolean) => {
      viewer.enableComposer(e);
    });
    cf.add(controls, "renderPassEnabled", controls.renderPassEnabled).name("RenderPass Enabled").onChange((e: boolean) => {
      viewer.enableRenderPass(e);
    });
    cf.add(controls, "fxaaEnabled", controls.fxaaEnabled).name("Effect FXAA Enabled").onChange((e: boolean) => {
      viewer.enableFxaaPass(e);
    });
    cf.add(controls, "saoEnabled", controls.saoEnabled).name("SAO Enabled").onChange((e: boolean) => {
      viewer.enableSaoPass(e);
    });
    cf.add(controls, "ssaoEnabled", controls.ssaoEnabled).name("SSAO Enabled").onChange((e: boolean) => {
      viewer.enableSsaoPass(e);
    });
    cf.add(controls, "outlineEnabled", controls.outlineEnabled).name("OutlinePass Enabled").onChange((e: boolean) => {
      viewer.enableOutlinePass(e);
    });
    cf.add(controls, "ssaaEnabled", controls.ssaaEnabled).name("SSAA Enabled").onChange((e: boolean) => {
      viewer.enableSsaaPass(e);
    });
    cf.add(controls, "bloomEnabled", controls.bloomEnabled).name("Bloom Enabled").onChange((e: boolean) => {
      viewer.enableBloomPass(e);
    });
    cf.add(controls, "unrealBloomEnabled", controls.unrealBloomEnabled).name("Unreal Bloom Enabled").onChange((e: boolean) => {
      viewer.enableUnrealBloomPass(e);
    });
  }

  private setExplodeMode(isExplodeMode: boolean, onlyExplodeUp = false) {
    if (!this.viewer || !this.viewer.scene || !this.viewer.loadedModels || !this.exploderDict) {
      return;
    }
    if (isExplodeMode) {
      SceneUtils.explodeObjects(this.viewer.scene, this.exploderDict, Object.values(this.viewer.loadedModels).map(obj => obj.uuid), onlyExplodeUp);
    } else {
      SceneUtils.unexplodeObjects(this.viewer.scene, this.exploderDict || {});
    }
  }

  // private filterFloor (floor: string) {
  //   if (this.viewer && this.viewer.scene && this.viewer.loadedModels) {
  //     const scene = this.viewer.scene
  //     const uuids = Object.values(this.viewer.loadedModels).map(obj => obj.uuid)
  //     if (floor) {
  //       const f = Number(floor.replace('F', ''))
  //       uuids.forEach(uuid => {
  //         ObjectUtils.setVisibleForFloors(scene, uuid, [f])
  //       })
  //     } else {
  //       uuids.forEach(uuid => {
  //         ObjectUtils.revertVisibleForFloorsByUuid(scene, uuid)
  //       })
  //     }
  //     this.viewer.enableRender()
  //   }
  // }

  private simEnableControllers: { [kind: string]: any } = {};
  private simLevelControllers: { [kind: string]: any } = {};
  private simFolder?: dat.GUI;

  /**
   * Ouvre le panneau dat.gui et déplie le dossier « Simulations » — utilisé
   * par le bouton flottant du viewer et l'auto-ouverture à l'activation.
   */
  openSimulations() {
    this.gui && this.gui.open();
    if (this.simFolder) {
      this.simFolder.open();
    }
  }

  private initPostmate() {
    const viewer = this.viewer;
    if (!viewer) {
      return;
    }
    this.postmate.addEventListenerWithReturnValue(MessageId.getGroundGrid, () => {
      return viewer.groundGrid && viewer.groundGrid.visible;
    });
    this.postmate.addEventListener(MessageId.setGroundGrid, (messageData: object) => {
      const value = (messageData as BooleanMessageData).value;
      viewer.groundGrid && (viewer.groundGrid.visible = value);
      viewer.enableRender();
    });
    this.postmate.addEventListener(MessageId.goHomeView, () => {
      viewer.goToHomeView();
    });
    this.postmate.addEventListener(MessageId.setTransparentMode, (messageData: object) => {
      const value = (messageData as BooleanMessageData).value;
      viewer.addOrRemoveObjectOpacity(value);
    });
    this.postmate.addEventListener(MessageId.setExplodeMode, (messageData: object) => {
      const value = (messageData as BooleanMessageData).value;
      this.setExplodeMode(value);
      viewer.enableRender();
    });
  }

  open() {
    this.gui && this.gui.open();
  }

  close() {
    this.gui && this.gui.close();
  }

  beforeDestroy() {
    this.viewer = undefined;
    this.gui && this.gui.destroy();
    this.gui = undefined;
    this.simFolder = undefined;
    this.exploderDict = [];
    this.postmate.removeEventListenerWithReturnValue(MessageId.getGroundGrid);
    this.postmate.removeEventListener(
      MessageId.setGroundGrid,
      MessageId.goHomeView,
      MessageId.setTransparentMode,
      MessageId.setExplodeMode);
  }
}
