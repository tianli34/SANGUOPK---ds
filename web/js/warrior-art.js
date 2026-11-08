/*
 * 文件名: warrior-art.js
 * 用途: 武将视觉素材层（可替换）
 *
 * 业务逻辑只依赖 resolveStyle / createRider / createPortrait 三个接口。
 * 以后接入精灵图或骨骼动画时，只需替换本文件内的实现，
 * 让 createRider 返回 <img> 或容器节点即可，动画与播放逻辑无需改动。
 */
(function () {
  "use strict";

  const PRESETS = {
    马超: {
      weapon: "spear",
      horse: "#d5c9b8",
      horseDark: "#ad9d87",
      mane: "#3a3340",
      armor: "#c6d2e4",
      armorDark: "#8b9bb3",
      metal: "#e6eef7",
      metalDark: "#8d9aad",
      accent: "#b02f2b",
      plume: "#e04b3c",
      skin: "#e6c6a0",
    },
    许褚: {
      weapon: "cleaver",
      horse: "#6b4a33",
      horseDark: "#4a3020",
      mane: "#241812",
      armor: "#8a6338",
      armorDark: "#5b3f22",
      metal: "#c9a25a",
      metalDark: "#7a5c2e",
      accent: "#2f3a48",
      plume: "#b23a2e",
      skin: "#d8b183",
    },
  };

  const FALLBACK_PALETTES = [
    {
      weapon: "spear",
      horse: "#b9b2a4",
      horseDark: "#8f887c",
      mane: "#312b28",
      armor: "#9aa7b8",
      armorDark: "#6c7888",
      metal: "#d9e2ee",
      metalDark: "#8996a6",
      accent: "#8d3a32",
      plume: "#c9483c",
      skin: "#e3c19a",
    },
    {
      weapon: "cleaver",
      horse: "#7c5a3d",
      horseDark: "#553a26",
      mane: "#2a1d15",
      armor: "#7b6b4a",
      armorDark: "#574a31",
      metal: "#b99a62",
      metalDark: "#7d6537",
      accent: "#3c4658",
      plume: "#a54a34",
      skin: "#d6ae82",
    },
  ];

  function escapeAttr(value) {
    return String(value).replace(/[&<>"']/g, (ch) => {
      const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
      return map[ch];
    });
  }

  function hashName(name) {
    let hash = 0;
    for (let i = 0; i < name.length; i += 1) {
      hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
    }
    return hash;
  }

  function resolveStyle(name) {
    if (PRESETS[name]) return { ...PRESETS[name], name };
    const base = FALLBACK_PALETTES[hashName(name) % FALLBACK_PALETTES.length];
    return { ...base, name };
  }

  function cssVars(style) {
    return [
      `--horse:${style.horse}`,
      `--horse-dark:${style.horseDark}`,
      `--mane:${style.mane}`,
      `--armor:${style.armor}`,
      `--armor-dark:${style.armorDark}`,
      `--metal:${style.metal}`,
      `--metal-dark:${style.metalDark}`,
      `--accent:${style.accent}`,
      `--plume:${style.plume}`,
      `--skin:${style.skin}`,
    ].join(";");
  }

  function spear() {
    return `
      <line x1="92" y1="198" x2="352" y2="38" stroke="#6d4f2f" stroke-width="7" stroke-linecap="round" />
      <line x1="104" y1="190" x2="338" y2="48" stroke="#a37a45" stroke-width="2" stroke-linecap="round" opacity=".7" />
      <path d="M347 28 L364 44 L338 54 Z" fill="var(--metal)" stroke="var(--metal-dark)" stroke-width="1.6" />
      <path d="M316 57 C330 52 340 60 344 72 C332 68 322 70 314 76 C314 68 314 62 316 57 Z" fill="var(--plume)" opacity=".92" />
      <circle cx="200" cy="120" r="6" fill="var(--metal-dark)" />
    `;
  }

  function cleaver() {
    return `
      <line x1="100" y1="190" x2="302" y2="76" stroke="#5d442c" stroke-width="8" stroke-linecap="round" />
      <line x1="112" y1="182" x2="296" y2="78" stroke="#9a7443" stroke-width="2" stroke-linecap="round" opacity=".65" />
      <path d="M298 66 C332 54 356 74 358 98 C340 92 322 100 308 116 C306 100 300 82 284 76 Z" fill="var(--metal)" stroke="var(--metal-dark)" stroke-width="2" />
      <path d="M306 86 C326 80 340 88 344 100" fill="none" stroke="var(--metal-dark)" stroke-width="2" opacity=".8" />
      <path d="M278 82 C290 78 298 86 300 96 C288 92 280 94 274 100 C274 92 274 86 278 82 Z" fill="var(--plume)" opacity=".9" />
      <circle cx="200" cy="120" r="6" fill="var(--metal-dark)" />
    `;
  }

  function createRider(style) {
    const weapon = style.weapon === "cleaver" ? cleaver() : spear();
    return `
      <svg class="rider-svg" viewBox="0 0 420 280" role="img" aria-label="${escapeAttr(style.name)}立绘">
        <g class="horse-figure">
          <path class="tail" d="M98 140 C74 142 54 158 34 188 C60 178 78 178 94 170 Z" fill="var(--horse-dark)" />
          <ellipse class="horse-body" cx="168" cy="158" rx="80" ry="42" fill="var(--horse)" />
          <path class="horse-neck" d="M222 156 C246 142 266 114 280 84 L316 96 C304 132 282 170 252 188 Z" fill="var(--horse)" />
          <path class="horse-head" d="M276 84 L322 96 L350 116 L344 138 L324 142 L294 122 L274 106 Z" fill="var(--horse)" />
          <path class="horse-ear" d="M294 86 L300 64 L314 86 Z" fill="var(--horse-dark)" />
          <circle class="horse-eye" cx="320" cy="111" r="3.4" fill="#1c1712" />
          <path class="mane" d="M284 80 C274 108 264 138 248 162 C266 154 280 136 292 108 Z" fill="var(--mane)" />
          <path class="horse-muzzle" d="M338 124 L348 130 L340 138" fill="none" stroke="var(--horse-dark)" stroke-width="2" />
          <path class="saddle" d="M136 128 C156 116 198 116 216 128 L208 154 C184 144 160 144 140 154 Z" fill="var(--accent)" />
          <path class="saddle-trim" d="M146 133 L206 133" stroke="var(--gold)" stroke-width="3" fill="none" opacity=".75" />
          <g class="leg leg-r-far" style="transform-origin:126px 184px">
            <path d="M126 184 L102 216 L92 246" fill="none" stroke="var(--horse-dark)" stroke-width="12" stroke-linecap="round" />
            <path d="M92 246 L78 250" fill="none" stroke="#2a2119" stroke-width="7" stroke-linecap="round" />
          </g>
          <g class="leg leg-r-near" style="transform-origin:112px 186px">
            <path d="M112 186 L118 220 L110 248" fill="none" stroke="var(--horse)" stroke-width="13" stroke-linecap="round" />
            <path d="M110 248 L96 252" fill="none" stroke="#2a2119" stroke-width="7" stroke-linecap="round" />
          </g>
          <g class="leg leg-f-far" style="transform-origin:218px 184px">
            <path d="M218 184 L226 216 L236 246" fill="none" stroke="var(--horse-dark)" stroke-width="12" stroke-linecap="round" />
            <path d="M236 246 L250 250" fill="none" stroke="#2a2119" stroke-width="7" stroke-linecap="round" />
          </g>
          <g class="leg leg-f-near" style="transform-origin:236px 186px">
            <path d="M236 186 L252 216 L262 246" fill="none" stroke="var(--horse)" stroke-width="13" stroke-linecap="round" />
            <path d="M262 246 L278 249" fill="none" stroke="#2a2119" stroke-width="7" stroke-linecap="round" />
          </g>
        </g>
        <g class="rider-figure">
          <path class="rider-leg" d="M160 144 C172 156 180 174 182 196" fill="none" stroke="var(--armor-dark)" stroke-width="15" stroke-linecap="round" />
          <path class="rider-boot" d="M172 190 L198 196 L196 208 L172 202 Z" fill="#33261c" />
          <path class="rider-skirt" d="M142 138 C150 158 164 168 182 170 L186 152 C170 148 158 140 152 130 Z" fill="var(--armor-dark)" />
          <path class="rider-torso" d="M141 150 C136 122 142 92 154 76 L181 72 C190 96 191 124 184 152 Z" fill="var(--armor)" />
          <path class="rider-sash" d="M148 116 L186 112 L186 121 L148 125 Z" fill="var(--accent)" opacity=".85" />
          <circle class="shoulder" cx="178" cy="92" r="15" fill="var(--metal)" opacity=".9" />
          <g class="rider-head">
            <circle cx="166" cy="56" r="17" fill="var(--skin)" />
            <path class="helmet" d="M146 54 C146 34 157 23 171 23 C185 23 194 35 194 52 L186 49 C183 38 178 33 169 33 C159 33 152 41 152 54 Z" fill="var(--metal)" />
            <path class="helmet-plate" d="M145 52 L195 50 L193 59 L147 61 Z" fill="var(--metal-dark)" />
            <path class="plume" d="M168 26 C156 8 132 5 116 14 C138 18 150 28 157 40 Z" fill="var(--plume)" />
            <path class="face-line" d="M154 63 C160 68 172 68 180 62" fill="none" stroke="#7a5b3d" stroke-width="2" opacity=".8" />
          </g>
          <g class="arm-group">
            <path class="upper-arm" d="M178 88 C190 94 198 104 200 116" fill="none" stroke="var(--armor)" stroke-width="15" stroke-linecap="round" />
            <g class="weapon">${weapon}</g>
          </g>
        </g>
      </svg>
    `;
  }

  function createPortrait(style) {
    const gradId = `portrait-grad-${hashName(style.name)}`;
    return `
      <svg viewBox="0 0 100 100" role="img" aria-label="${escapeAttr(style.name)}头像">
        <defs>
          <radialGradient id="${gradId}" cx="50%" cy="38%" r="65%">
            <stop offset="0%" stop-color="var(--portrait-glow)" />
            <stop offset="100%" stop-color="rgba(8,11,16,.95)" />
          </radialGradient>
        </defs>
        <circle cx="50" cy="50" r="49" fill="url(#${gradId})" />
        <circle cx="50" cy="50" r="47" fill="none" stroke="var(--gold)" stroke-opacity=".45" stroke-width="1.4" />
        <path d="M18 92 C22 72 36 64 50 64 C64 64 78 72 82 92 Z" fill="var(--armor)" />
        <path d="M36 68 C40 78 60 78 64 68 L62 82 C56 86 44 86 38 82 Z" fill="var(--armor-dark)" />
        <path d="M40 92 L50 78 L60 92 Z" fill="var(--accent)" opacity=".85" />
        <circle cx="50" cy="47" r="19" fill="var(--skin)" />
        <path d="M30 45 C30 26 40 17 51 17 C63 17 71 27 71 43 L65 40 C62 30 57 26 50 26 C42 26 36 33 36 45 Z" fill="var(--metal)" />
        <path d="M30 43 L71 41 L69 49 L31 51 Z" fill="var(--metal-dark)" />
        <path d="M50 20 C42 8 25 8 19 15 C34 16 43 22 47 30 Z" fill="var(--plume)" />
        <path d="M42 51 C46 55 55 55 59 50" fill="none" stroke="#6e4f35" stroke-width="1.8" opacity=".85" />
      </svg>
    `;
  }

  window.WarriorArt = { resolveStyle, createRider, createPortrait, cssVars };
})();
