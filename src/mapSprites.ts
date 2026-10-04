import type { Map as MapboxMap } from "mapbox-gl";

type SpriteName = "bottle" | "bag" | "foam" | "collector";

function makeCanvas(name: SpriteName): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = 96;
  canvas.height = 96;
  const context = canvas.getContext("2d");
  if (!context) return canvas;

  context.lineCap = "round";
  context.lineJoin = "round";
  context.lineWidth = 6;
  context.strokeStyle = "#173b50";

  if (name === "bottle") {
    context.fillStyle = "#56c596";
    context.beginPath();
    context.roundRect(31, 29, 34, 53, 12);
    context.fill();
    context.stroke();
    context.fillStyle = "#ffd45a";
    context.fillRect(38, 16, 20, 16);
    context.strokeRect(38, 16, 20, 16);
    context.fillStyle = "#ffffff";
    context.fillRect(33, 47, 30, 14);
    return canvas;
  }

  if (name === "bag") {
    context.fillStyle = "#ff8daa";
    context.beginPath();
    context.roundRect(20, 31, 56, 50, 10);
    context.fill();
    context.stroke();
    context.beginPath();
    context.arc(48, 34, 17, Math.PI, 0);
    context.stroke();
    context.fillStyle = "#173b50";
    context.beginPath();
    context.arc(38, 55, 3, 0, Math.PI * 2);
    context.arc(58, 55, 3, 0, Math.PI * 2);
    context.fill();
    return canvas;
  }

  if (name === "foam") {
    context.fillStyle = "#fff6d9";
    context.beginPath();
    context.roundRect(17, 31, 62, 43, 12);
    context.fill();
    context.stroke();
    context.beginPath();
    context.moveTo(20, 48);
    context.lineTo(76, 48);
    context.stroke();
    context.fillStyle = "#ffd45a";
    context.beginPath();
    context.arc(32, 61, 5, 0, Math.PI * 2);
    context.arc(48, 61, 5, 0, Math.PI * 2);
    context.arc(64, 61, 5, 0, Math.PI * 2);
    context.fill();
    return canvas;
  }

  context.fillStyle = "#ffcc4d";
  context.beginPath();
  context.arc(48, 48, 27, 0, Math.PI * 2);
  context.fill();
  context.stroke();
  context.fillStyle = "#ffffff";
  context.beginPath();
  context.arc(48, 48, 10, 0, Math.PI * 2);
  context.fill();
  context.stroke();
  context.strokeStyle = "#ff6b6b";
  context.lineWidth = 8;
  context.beginPath();
  context.arc(48, 48, 27, -0.55, 0.55);
  context.arc(48, 48, 27, Math.PI - 0.55, Math.PI + 0.55);
  context.stroke();
  return canvas;
}

export function registerMapSprites(map: MapboxMap) {
  const names: SpriteName[] = ["bottle", "bag", "foam", "collector"];
  names.forEach((name) => {
    const canvas = makeCanvas(name);
    const context = canvas.getContext("2d");
    if (!map.hasImage(name) && context) {
      map.addImage(name, context.getImageData(0, 0, canvas.width, canvas.height), { pixelRatio: 2 });
    }
  });
}
