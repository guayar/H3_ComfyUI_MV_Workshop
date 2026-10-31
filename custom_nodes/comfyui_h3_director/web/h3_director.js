// Rozszerzenie frontendu ComfyUI: przycisk „Otworz panel H3 Director” na wezle H3Director.
// [UNVERIFIED w Twoim ComfyUI] Import "../../scripts/app.js" jest zgodny z konwencja custom nodes,
// ale API frontendu zmienia sie miedzy wersjami. Jesli wezel nie ma przycisku, sprawdz konsole przegladarki.
import { app } from "../../scripts/app.js";

const PANEL_URL = new URL("./h3_director_panel.html", import.meta.url).href;

app.registerExtension({
  name: "H3.Director",
  nodeCreated(node) {
    if (node.comfyClass !== "H3Director") return;

    const planWidget = node.widgets?.find((w) => w.name === "plan_json");
    if (!planWidget) {
      console.warn("H3Director: brak widgetu plan_json");
      return;
    }

    let panelWindow = null;

    node.addWidget("button", "Otworz panel H3 Director", null, () => {
      panelWindow = window.open(PANEL_URL, "h3_director_panel", "width=1200,height=860");
      if (!panelWindow) {
        alert("Przegladarka zablokowala okno. Zezwol na wyskakujace okna dla tej strony.");
      }
    });

    // Panel -> wezel: aktualny plan po kazdej zmianie
    window.addEventListener("message", (ev) => {
      if (!panelWindow || ev.source !== panelWindow) return;
      const data = ev.data || {};
      if (data.type === "h3-plan-update" && typeof data.plan === "string") {
        planWidget.value = data.plan;
        node.setDirtyCanvas?.(true, true);
      }
      if (data.type === "h3-plan-request") {
        panelWindow.postMessage({ type: "h3-plan-init", plan: planWidget.value }, "*");
      }
    });
  },
});
