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
    关羽: {
      weapon: "guandao",
      horse: "#8a3b2e",
      horseDark: "#5c241c",
      mane: "#241110",
      armor: "#2f6b4d",
      armorDark: "#1f4a35",
      metal: "#d9c27a",
      metalDark: "#8f7534",
      accent: "#a8322b",
      plume: "#c0392b",
      skin: "#c98a6a",
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

  /* 精灵图数据由 tools/build_sprite.py 生成，按武将名称索引 */
  const SPRITES = window.WarriorSprites || {};

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

  function hasSprite(name) {
    return Boolean(SPRITES[name]);
  }

  const spriteStyles = new Set();

  /* 图集只有 1/5/6/7/8 五个朝向：左半边由右侧条带镜像得到 */
  const FACING_DIRS = {
    r: "7",
    ur: "6",
    u: "5",
    dr: "8",
    d: "1",
    l: "7",
    ul: "6",
    dl: "8",
  };
  const FACINGS = ["r", "ur", "u", "dr", "d", "l", "ul", "dl"];

  /**
   * 每个武将的动作条带宽度、步进数与时长都不同，按需注入一组 CSS 动画：
   * 循环动作用 steps(N) 走到 -100%；一次性动作停在最后一帧，配合 forwards。
   * data-facing 由 scene.js 按相对方位设置，未设置时退回朝右条带。
   */
  function ensureSpriteStyles(name) {
    const sprite = SPRITES[name];
    if (!sprite || spriteStyles.has(sprite.slug)) return sprite;
    spriteStyles.add(sprite.slug);

    const sel = `[data-sprite="${sprite.slug}"]`;
    const dirs = sprite.dirs || {};
    const fallbackKey = dirs["7"] ? "7" : Object.keys(dirs)[0];
    const fallback = dirs[fallbackKey];
    if (!fallback) return sprite;

    const holdOffset = (frames) => (((frames - 1) / frames) * 100).toFixed(4);
    const holdName = (dir, action) => `sprite-hold-${sprite.slug}-${dir}-${action}`;

    const keyframes = Object.keys(dirs)
      .map((dir) => {
        const { attack, stuck, die } = dirs[dir];
        return `
          @keyframes ${holdName(dir, "attack")} {
            from { transform: translateX(0); }
            to { transform: translateX(-${holdOffset(attack.frames)}%); }
          }
          @keyframes ${holdName(dir, "stuck")} {
            from { transform: translateX(0); }
            to { transform: translateX(-${holdOffset(stuck.frames)}%); }
          }
          @keyframes ${holdName(dir, "die")} {
            from { transform: translateX(0); }
            to { transform: translateX(-${holdOffset(die.frames)}%); }
          }`;
      })
      .join("");

    const idleCss = (group) => `
        width: ${group.frames * 100}%;
        background-image: url("${group.src}");
        animation: sprite-slide ${group.frames * group.ms}ms steps(${group.frames}, end) infinite;`;

    const rules = FACINGS.map((facing) => {
      const dir = FACING_DIRS[facing];
      const group = dirs[dir] || fallback;
      const { idle, run, attack, stuck, die } = group;
      return `
        .unit[data-facing="${facing}"] ${sel} .sprite-strip {${idleCss(idle)}
        }
        .unit.moving[data-facing="${facing}"] ${sel} .sprite-strip {
          background-image: url("${run.src}");
          width: ${run.frames * 100}%;
          animation: sprite-slide calc(${run.frames * run.ms}ms * var(--beat)) steps(${run.frames}, end) infinite;
        }
        .unit.attacking[data-facing="${facing}"] ${sel} .sprite-strip,
        .unit.countering[data-facing="${facing}"] ${sel} .sprite-strip {
          background-image: url("${attack.src}");
          width: ${attack.frames * 100}%;
          animation: ${holdName(dir, "attack")} calc(${attack.frames * attack.ms}ms * var(--beat)) steps(${attack.frames - 1}, end) forwards;
        }
        .unit.hit[data-facing="${facing}"] ${sel} .sprite-strip {
          background-image: url("${stuck.src}");
          width: ${stuck.frames * 100}%;
          animation: ${holdName(dir, "stuck")} calc(${stuck.frames * stuck.ms}ms * var(--beat)) steps(${stuck.frames - 1}, end) forwards;
        }
        .unit.fallen[data-facing="${facing}"] ${sel} .sprite-strip {
          background-image: url("${die.src}");
          width: ${die.frames * 100}%;
          animation: ${holdName(dir, "die")} calc(${die.frames * die.ms}ms * var(--beat)) steps(${die.frames - 1}, end) forwards;
        }
        .unit.fallen-instant[data-facing="${facing}"] ${sel} .sprite-strip {
          background-image: url("${die.src}");
          width: ${die.frames * 100}%;
          animation: none;
          transform: translateX(-${holdOffset(die.frames)}%);
        }`;
    }).join("");

    const baseIdle = fallback.idle;

    const baseRules = `
      .unit.moving ${sel} .sprite-strip {
        background-image: url("${fallback.run.src}");
        width: ${fallback.run.frames * 100}%;
        animation: sprite-slide calc(${fallback.run.frames * fallback.run.ms}ms * var(--beat)) steps(${fallback.run.frames}, end) infinite;
      }
      .unit.attacking ${sel} .sprite-strip,
      .unit.countering ${sel} .sprite-strip {
        background-image: url("${fallback.attack.src}");
        width: ${fallback.attack.frames * 100}%;
        animation: ${holdName(fallbackKey, "attack")} calc(${fallback.attack.frames * fallback.attack.ms}ms * var(--beat)) steps(${fallback.attack.frames - 1}, end) forwards;
      }
      .unit.hit ${sel} .sprite-strip {
        background-image: url("${fallback.stuck.src}");
        width: ${fallback.stuck.frames * 100}%;
        animation: ${holdName(fallbackKey, "stuck")} calc(${fallback.stuck.frames * fallback.stuck.ms}ms * var(--beat)) steps(${fallback.stuck.frames - 1}, end) forwards;
      }
      .unit.fallen ${sel} .sprite-strip {
        background-image: url("${fallback.die.src}");
        width: ${fallback.die.frames * 100}%;
        animation: ${holdName(fallbackKey, "die")} calc(${fallback.die.frames * fallback.die.ms}ms * var(--beat)) steps(${fallback.die.frames - 1}, end) forwards;
      }
      .unit.fallen-instant ${sel} .sprite-strip {
        background-image: url("${fallback.die.src}");
        width: ${fallback.die.frames * 100}%;
        animation: none;
        transform: translateX(-${holdOffset(fallback.die.frames)}%);
      }`;

    const css = `
      @keyframes sprite-slide {
        from { transform: translateX(0); }
        to { transform: translateX(-100%); }
      }
      ${keyframes}
      ${sel} .sprite-viewport { aspect-ratio: ${sprite.cell[0]} / ${sprite.cell[1]}; }
      ${sel} .sprite-strip {${idleCss(baseIdle)}
      }
      ${baseRules}
      ${rules}
    `;

    const style = document.createElement("style");
    style.id = `sprite-style-${sprite.slug}`;
    style.textContent = css;
    document.head.appendChild(style);
    return sprite;
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

  function guandao() {
    return `
      <line x1="88" y1="202" x2="330" y2="42" stroke="#5d442c" stroke-width="8" stroke-linecap="round" />
      <line x1="100" y1="194" x2="322" y2="48" stroke="#a37a45" stroke-width="2" stroke-linecap="round" opacity=".65" />
      <path d="M310 36 C338 22 366 34 376 58 C382 70 378 84 368 94 C360 78 346 66 328 60 C318 57 310 48 310 36 Z" fill="var(--metal)" stroke="var(--metal-dark)" stroke-width="2" />
      <path d="M318 48 C340 40 358 46 366 62" fill="none" stroke="var(--metal-dark)" stroke-width="2" opacity=".8" />
      <path d="M306 84 C316 78 324 84 326 94 C316 90 308 92 302 98 C302 90 302 86 306 84 Z" fill="var(--plume)" opacity=".9" />
      <circle cx="210" cy="120" r="6" fill="var(--metal-dark)" />
    `;
  }

  function createSpriteRider(style) {
    const sprite = ensureSpriteStyles(style.name);
    return `
      <div class="sprite-rider" data-sprite="${escapeAttr(sprite.slug)}">
        <div class="sprite-viewport"><div class="sprite-strip"></div></div>
      </div>
    `;
  }

  function createRider(style) {
    if (hasSprite(style.name)) return createSpriteRider(style);
    const weapon =
      style.weapon === "cleaver"
        ? cleaver()
        : style.weapon === "guandao"
        ? guandao()
        : spear();
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
    const sprite = SPRITES[style.name];
    if (sprite && sprite.portrait) {
      return `<img class="sprite-portrait" src="${escapeAttr(sprite.portrait)}" alt="${escapeAttr(style.name)}头像" />`;
    }
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

  window.WarriorArt = { resolveStyle, createRider, createPortrait, cssVars, hasSprite };
})();
