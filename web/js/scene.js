/*
 * 文件名: scene.js
 * 用途: 根据结构化战斗事件驱动战场演出
 *
 * 本文件不产生任何随机战斗结果：攻击是否命中、伤害与体力变化
 * 全部读取事件 JSON，仅负责“怎么演”。
 */
(function () {
  "use strict";

  const POSES = ["attacking", "guarding", "dodging", "parrying", "countering", "hit", "ready"];
  const DEFENSE_POSE = {
    block: "guarding",
    parry: "parrying",
    dodge: "dodging",
    counter: "countering",
  };
  const DEFENSE_VERB = { block: "格挡", parry: "招架", dodge: "闪避", counter: "反击" };

  class Scene {
    constructor() {
      this.stage = document.getElementById("stage");
      this.fxLayer = document.getElementById("fx-layer");
      this.floatLayer = document.getElementById("float-layer");
      this.units = {
        A: document.getElementById("unit-A"),
        B: document.getElementById("unit-B"),
      };
      this.defenseBanner = document.getElementById("defense-banner");
      this.defWord = document.getElementById("def-word");
      this.defResult = document.getElementById("def-result");
      this.clashBanner = document.getElementById("clash-banner");

      this.speed = 1;
      this.paused = false;
      this.generation = 0;
      this.floatStacks = { A: 0, B: 0 };
      this.defSeq = 0;
      this.clashSeq = 0;
      this.warriors = null;
      this.map = null;
      this.mapGrid = document.getElementById("map-grid");
      this.cells = [];
      this.positions = { A: null, B: null };
      this.rangeOn = false;
    }

    init(doc) {
      this.warriors = doc.warriors;
      const styleA = window.WarriorArt.resolveStyle(doc.warriors.A.name);
      const styleB = window.WarriorArt.resolveStyle(doc.warriors.B.name);

      document.getElementById("mirror-A").innerHTML = window.WarriorArt.createRider(styleA);
      document.getElementById("mirror-B").innerHTML = window.WarriorArt.createRider(styleB);
      document.getElementById("portrait-A").style.cssText = window.WarriorArt.cssVars(styleA);
      document.getElementById("portrait-B").style.cssText = window.WarriorArt.cssVars(styleB);
      document.getElementById("portrait-A").innerHTML = window.WarriorArt.createPortrait(styleA);
      document.getElementById("portrait-B").innerHTML = window.WarriorArt.createPortrait(styleB);

      this.units.A.style.cssText = window.WarriorArt.cssVars(styleA);
      this.units.B.style.cssText = window.WarriorArt.cssVars(styleB);

      this.setupMap(doc);
      this.spawnDust();
      this.setSpeed(this.speed || 1);
    }

    /* ---------------- 地图模式（version 2） ---------------- */

    setupMap(doc) {
      this.map = doc.map || null;
      this.rangeOn = false;
      this.cells = [];
      this.mapGrid.innerHTML = "";
      this.stage.classList.toggle("has-map", Boolean(this.map));
      document.getElementById("btn-range").hidden = !this.map;
      ["A", "B"].forEach((side) => this.units[side].classList.remove("face-left"));
      if (!this.map) {
        this.mapGrid.hidden = true;
        this.positions = { A: null, B: null };
        return;
      }
      this.mapGrid.hidden = false;
      this.mapGrid.style.gridTemplateColumns = `repeat(${this.map.width}, 1fr)`;
      this.mapGrid.style.gridTemplateRows = `repeat(${this.map.height}, 1fr)`;
      const rocks = new Set(this.map.obstacles.map(([x, y]) => `${x},${y}`));
      for (let y = 0; y < this.map.height; y += 1) {
        for (let x = 0; x < this.map.width; x += 1) {
          const cell = document.createElement("div");
          cell.className = "map-cell";
          if (rocks.has(`${x},${y}`)) cell.classList.add("is-rock");
          this.mapGrid.appendChild(cell);
          this.cells.push({ x, y, el: cell, rock: rocks.has(`${x},${y}`) });
        }
      }
      ["A", "B"].forEach((side) => {
        const spawn = this.map.spawns[side];
        this.positions[side] = { x: spawn[0], y: spawn[1] };
        this.placeUnit(side, spawn[0], spawn[1]);
      });
      this.updateFacing();
      this.updateRange();
    }

    /** 把单位锚定到格子中心（坐标可为小数，用于移动插值） */
    placeUnit(side, x, y) {
      const unit = this.units[side];
      unit.style.left = `${((x + 0.5) / this.map.width) * 100}%`;
      unit.style.top = `${((y + 0.5) / this.map.height) * 100}%`;
      unit.style.zIndex = String(10 + Math.round(y));
    }

    anchorPercent(side) {
      const pos = this.positions[side];
      return {
        x: ((pos.x + 0.5) / this.map.width) * 100,
        y: ((pos.y + 0.5) / this.map.height) * 100,
      };
    }

    facingDir(side) {
      if (!this.map) return side === "A" ? 1 : -1;
      return this.units[side].classList.contains("face-left") ? -1 : 1;
    }

    /** 朝向动态化：始终面向对手，同列时保持默认朝向 */
    updateFacing() {
      if (!this.map || !this.positions.A || !this.positions.B) return;
      ["A", "B"].forEach((side) => {
        const other = side === "A" ? "B" : "A";
        const dx = this.positions[other].x - this.positions[side].x;
        const dir = dx === 0 ? (side === "A" ? 1 : -1) : Math.sign(dx);
        const unit = this.units[side];
        unit.style.setProperty("--dir", String(dir));
        unit.classList.toggle("face-left", dir === -1);
      });
    }

    toggleRange() {
      this.rangeOn = !this.rangeOn;
      this.updateRange();
      return this.rangeOn;
    }

    /** 射程格高亮：双方当前站位切比雪夫距离 <= 各自射程的可站立格 */
    updateRange() {
      if (!this.map) return;
      this.cells.forEach((cell) => cell.el.classList.remove("in-range-a", "in-range-b"));
      if (!this.rangeOn) return;
      ["A", "B"].forEach((side) => {
        const pos = this.positions[side];
        if (!pos || this.units[side].classList.contains("fallen")) return;
        const weapon = this.warriors[side].weapon;
        const reach = (weapon && weapon.reach) || 1;
        this.cells.forEach((cell) => {
          if (cell.rock) return;
          const dist = Math.max(Math.abs(cell.x - pos.x), Math.abs(cell.y - pos.y));
          if (dist <= reach) cell.el.classList.add(side === "A" ? "in-range-a" : "in-range-b");
        });
      });
    }

    /** rAF 补间：暂停冻结、倍速实时生效、回退即作废；不用 CSS transition */
    tween(baseMs, onFrame, gen) {
      return new Promise((resolve) => {
        let elapsed = 0;
        let last = performance.now();
        const step = (now) => {
          if (gen !== this.generation) return resolve(false);
          if (!this.paused) elapsed += (now - last) * this.speed;
          last = now;
          const t = Math.min(1, elapsed / baseMs);
          onFrame(t);
          if (t >= 1) return resolve(true);
          window.requestAnimationFrame(step);
        };
        window.requestAnimationFrame(step);
      });
    }

    async moveUnit(ev, gen) {
      if (!this.map || !ev.move || !ev.move.side) {
        await this.wait(this.ms(120));
        return;
      }
      const side = ev.move.side;
      const from = ev.move.from;
      const to = ev.move.to;
      const ok = await this.tween(240, (t) => {
        const x = from[0] + (to[0] - from[0]) * t;
        const y = from[1] + (to[1] - from[1]) * t;
        this.positions[side] = { x, y };
        this.placeUnit(side, x, y);
        this.updateFacing();
      }, gen);
      if (!ok || gen !== this.generation) return;
      this.positions[side] = { x: to[0], y: to[1] };
      this.placeUnit(side, to[0], to[1]);
      this.updateFacing();
      this.updateRange();
    }

    spawnDust() {
      const dust = document.getElementById("dust");
      if (!dust) return;
      dust.innerHTML = "";
      for (let i = 0; i < 26; i += 1) {
        const particle = document.createElement("span");
        particle.style.left = `${Math.random() * 100}%`;
        particle.style.animationDuration = `${9 + Math.random() * 13}s`;
        particle.style.animationDelay = `${-Math.random() * 18}s`;
        particle.style.opacity = String(0.25 + Math.random() * 0.55);
        dust.appendChild(particle);
      }
    }

    setSpeed(speed) {
      this.speed = speed;
      this.stage.style.setProperty("--beat", String(1 / speed));
    }

    setPaused(paused) {
      this.paused = paused;
      this.stage.classList.toggle("is-paused", paused);
    }

    ms(base) {
      return base / this.speed;
    }

    wait(ms) {
      const gen = this.generation;
      return new Promise((resolve) => {
        let remaining = Math.max(0, ms);
        let last = performance.now();
        const step = () => {
          if (gen !== this.generation) return resolve(false);
          const now = performance.now();
          if (!this.paused) remaining -= now - last;
          last = now;
          if (remaining <= 0) return resolve(true);
          window.setTimeout(step, 32);
        };
        step();
      });
    }

    /** 与播放/暂停同步的延时清理，避免暂停时特效被真实时间清掉 */
    later(ms, callback) {
      this.wait(this.ms(ms)).then((ok) => {
        if (ok) callback();
      });
    }

    /** 回退 / 重播时停止所有正在进行的演出 */
    cancel() {
      this.generation += 1;
      this.fxLayer.innerHTML = "";
      this.floatLayer.innerHTML = "";
      this.floatStacks = { A: 0, B: 0 };
      this.defenseBanner.hidden = true;
      this.clashBanner.hidden = true;
      this.stage.querySelectorAll(".skill-toast, .unit-mark, .ghost, .slash-fx, .ring-fx, .arc-fx, .spark").forEach((node) => node.remove());
      this.stage.classList.remove("shake");
      this.defSeq += 1;
      this.clashSeq += 1;
      Object.keys(this.units).forEach((side) => {
        const unit = this.units[side];
        POSES.forEach((pose) => unit.classList.remove(pose));
        unit.classList.remove("fallen");
        unit.classList.remove("fallen-instant");
      });
    }

    /** 按快照重建静态战场（不播放动画） */
    restore(state) {
      this.cancel();
      if (this.map) {
        ["A", "B"].forEach((side) => {
          const entry = state && state[side];
          const pos = entry && entry.position ? entry.position : this.map.spawns[side];
          this.positions[side] = { x: pos[0], y: pos[1] };
          this.placeUnit(side, pos[0], pos[1]);
        });
        this.updateFacing();
      }
      Object.keys(this.units).forEach((side) => {
        const alive = state && state[side] ? state[side].alive : true;
        if (!alive) {
          this.units[side].classList.add("fallen", "fallen-instant");
        }
      });
      this.updateRange();
    }

    async pose(side, className, baseMs) {
      const unit = this.units[side];
      unit.classList.remove(className);
      void unit.offsetWidth;
      unit.classList.add(className);
      const ok = await this.wait(this.ms(baseMs));
      unit.classList.remove(className);
      return ok;
    }

    async both(promises) {
      await Promise.all(promises);
    }

    contactPoint(attackerSide) {
      if (this.map && this.positions.A && this.positions.B) {
        const a = this.anchorPercent("A");
        const b = this.anchorPercent("B");
        return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 6 };
      }
      return attackerSide === "A"
        ? { x: 55, y: 45 }
        : { x: 45, y: 45 };
    }

    /* ---------------- 事件入口 ---------------- */

    async animateEvent(ev, beforeState, onImpact) {
      const gen = this.generation;
      switch (ev.type) {
        case "battle_start":
          await this.battleStart(gen);
          break;
        case "skill_trigger":
          await this.skillTrigger(ev, gen);
          break;
        case "attack":
          await this.attack(ev, beforeState, onImpact, gen);
          break;
        case "move":
          await this.moveUnit(ev, gen);
          break;
        case "clash":
          await this.clash(ev, beforeState, onImpact, gen);
          break;
        case "sp_leader_change":
          await this.leaderChange(ev, gen);
          break;
        case "round_end":
          await this.wait(this.ms(120));
          break;
        default:
          await this.wait(this.ms(260));
      }
    }

    async battleStart(gen) {
      const a = this.pose("A", "ready", 800);
      const b = this.pose("B", "ready", 800);
      await this.wait(this.ms(260));
      if (gen !== this.generation) return;
      this.toast("两将出阵", { center: true });
      await this.both([a, b]);
    }

    async skillTrigger(ev, gen) {
      if (gen !== this.generation) return;
      const side = ev.skill && ev.skill.warrior === this.warriors.B.name ? "B" : "A";
      const text = ev.skill ? `特技 · ${ev.skill.name}` : "特技发动";
      const sub = ev.skill && ev.skill.amount ? `行动点数 +${ev.skill.amount}` : "";
      this.toast(text, { side, sub });
      await this.pose(side, "ready", 700);
    }

    async attack(ev, beforeState, onImpact, gen) {
      const atk = ev.actor.side;
      const def = ev.defender.side;
      const defense = ev.defense;
      const isCounter = defense.type === "counter";
      const contact = this.contactPoint(atk);
      const atkPose = this.pose(atk, "attacking", 700);

      await this.wait(this.ms(210));
      if (gen !== this.generation) return;

      this.slash(contact.x, contact.y, this.facingDir(atk) === -1);
      const defPose = this.pose(def, DEFENSE_POSE[defense.type] || "guarding", isCounter ? 780 : 620);
      this.showDefense(def, defense);

      if (defense.type === "block") {
        this.sparks(contact.x, contact.y, "#ffe0a0");
        this.ring(contact.x, contact.y);
        this.shake();
      } else if (defense.type === "parry") {
        this.arc(def);
        this.sparks(contact.x, contact.y, "#bfe8ff");
      } else if (defense.type === "dodge") {
        if (defense.success) this.ghost(def);
      } else if (isCounter) {
        this.arc(def);
      }

      if (isCounter) {
        await this.wait(this.ms(150));
        if (gen !== this.generation) return;
        this.slash(contact.x, contact.y, this.facingDir(def) === -1);
        this.sparks(contact.x, contact.y, "#ffcf8a");
        await this.wait(this.ms(40));
      }
      if (gen !== this.generation) return;

      if (onImpact) onImpact();
      this.spawnFloating(ev);

      const hits = [];
      [def, atk].forEach((side) => {
        if (!ev.alive[side]) return;
        if (ev.effects[side] && ev.effects[side].hp < -0.5) {
          hits.push(this.pose(side, "hit", 420));
        }
      });

      await this.reactToDeaths(ev, beforeState);
      await this.both([atkPose, defPose, ...hits]);
    }

    async clash(ev, beforeState, onImpact, gen) {
      this.clashBanner.hidden = false;
      this.clashBanner.classList.remove("show");
      void this.clashBanner.offsetWidth;
      this.clashBanner.classList.add("show");
      const clashSeq = ++this.clashSeq;
      this.later(900, () => {
        if (clashSeq === this.clashSeq) this.clashBanner.hidden = true;
      });

      const aPose = this.pose("A", "attacking", 900);
      const bPose = this.pose("B", "attacking", 900);
      await this.wait(this.ms(380));
      if (gen !== this.generation) return;

      this.sparks(50, 45, "#ffe6ac");
      this.ring(50, 45);
      this.slash(50, 45, false);
      this.shake();
      if (onImpact) onImpact();
      this.spawnFloating(ev);
      await this.reactToDeaths(ev, beforeState);
      await this.both([aPose, bPose]);
    }

    async leaderChange(ev, gen) {
      if (gen !== this.generation) return;
      const side = ev.leader;
      const name = side && this.warriors[side] ? this.warriors[side].name : "";
      this.toast(name ? `体力领先 → ${name}` : "体力领先易主", { center: true });
      await this.wait(this.ms(360));
    }

    /* ---------------- 反馈层 ---------------- */

    showDefense(side, defense) {
      const banner = this.defenseBanner;
      banner.hidden = false;
      banner.classList.remove("at-a", "at-b", "show");
      banner.classList.add(side === "A" ? "at-a" : "at-b");
      banner.style.left = this.map && this.positions[side] ? `${this.anchorPercent(side).x}%` : "";
      this.defWord.textContent = defense.label || DEFENSE_VERB[defense.type] || "防御";
      this.defResult.textContent = defense.success ? "成功" : "失败";
      this.defResult.className = `def-result ${defense.success ? "is-success" : "is-fail"}`;
      void banner.offsetWidth;
      banner.classList.add("show");
      const seq = ++this.defSeq;
      this.later(1150, () => {
        if (seq === this.defSeq) banner.hidden = true;
      });
    }

    spawnFloating(ev) {
      const effects = ev.effects || {};
      ["A", "B"].forEach((side) => {
        const fx = effects[side];
        if (!fx) return;
        if (fx.hp < -0.5) this.addFloat(side, "hp", fx.hp);
        if (fx.sp < -0.4 || fx.sp > 0.4) this.addFloat(side, "sp", fx.sp);
        if (fx.courage !== 0) this.addFloat(side, "courage", fx.courage);
      });
    }

    addFloat(side, kind, value) {
      const rounded = Math.round(value);
      if (rounded === 0) return;
      const stack = Math.min(this.floatStacks[side], 5);
      const node = document.createElement("div");
      node.className = `float-num is-${kind}`;
      node.textContent = `${value > 0 ? "+" : ""}${rounded}`;
      let baseX = side === "A" ? 29 : 71;
      let baseY = 44;
      if (this.map && this.positions[side]) {
        const anchor = this.anchorPercent(side);
        baseX = anchor.x;
        baseY = anchor.y - 16;
      }
      node.style.left = `${baseX + (Math.random() * 5 - 2.5)}%`;
      node.style.top = `${baseY - stack * 7}%`;
      this.floatLayer.appendChild(node);
      this.floatStacks[side] += 1;
      this.later(1250, () => {
        node.remove();
        this.floatStacks[side] = Math.max(0, this.floatStacks[side] - 1);
      });
    }

    slash(x, y, flip) {
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 190 130");
      svg.classList.add("slash-fx");
      svg.style.left = `${x}%`;
      svg.style.top = `${y}%`;
      if (flip) svg.style.transform = "translate(-50%, -50%) scaleX(-1)";

      const glow = document.createElementNS("http://www.w3.org/2000/svg", "path");
      glow.setAttribute("d", "M14 112 C62 84 112 36 176 18");
      glow.setAttribute("stroke", "rgba(255,204,120,.45)");
      glow.setAttribute("stroke-width", "12");
      glow.setAttribute("filter", "blur(3px)");
      const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
      line.setAttribute("d", "M14 112 C62 84 112 36 176 18");
      svg.appendChild(glow);
      svg.appendChild(line);
      this.fxLayer.appendChild(svg);
      this.later(760, () => svg.remove());
    }

    sparks(x, y, color) {
      for (let i = 0; i < 14; i += 1) {
        const spark = document.createElement("span");
        spark.className = "spark";
        const angle = Math.random() * Math.PI * 2;
        const distance = 22 + Math.random() * 58;
        spark.style.left = `${x}%`;
        spark.style.top = `${y}%`;
        spark.style.background = color || "#ffe9b0";
        spark.style.setProperty("--dx", `${Math.cos(angle) * distance}px`);
        spark.style.setProperty("--dy", `${Math.sin(angle) * distance}px`);
        this.fxLayer.appendChild(spark);
        this.later(820, () => spark.remove());
      }
    }

    ring(x, y) {
      const ring = document.createElement("div");
      ring.className = "ring-fx";
      ring.style.left = `${x}%`;
      ring.style.top = `${y}%`;
      this.fxLayer.appendChild(ring);
      this.later(720, () => ring.remove());
    }

    arc(side) {
      const arc = document.createElement("div");
      arc.className = "arc-fx";
      if (this.map && this.positions[side]) {
        const anchor = this.anchorPercent(side);
        arc.style.left = `${anchor.x}%`;
        arc.style.top = `${anchor.y - 8}%`;
      } else {
        arc.style.left = side === "A" ? "31%" : "69%";
        arc.style.top = "47%";
      }
      this.fxLayer.appendChild(arc);
      this.later(760, () => arc.remove());
    }

    ghost(side) {
      const inner = this.units[side].querySelector(".unit-inner");
      if (!inner) return;
      const ghost = inner.cloneNode(true);
      ghost.classList.add("ghost");
      this.units[side].appendChild(ghost);
      this.later(720, () => ghost.remove());
    }

    shake() {
      this.stage.classList.add("shake");
      this.later(460, () => this.stage.classList.remove("shake"));
    }

    toast(text, options = {}) {
      const node = document.createElement("div");
      node.className = "skill-toast";
      if (options.center) {
        node.classList.add("center");
      } else if (options.side) {
        node.classList.add(options.side === "A" ? "at-a" : "at-b");
      }
      node.textContent = text;
      if (options.sub) {
        const small = document.createElement("small");
        small.textContent = options.sub;
        node.appendChild(small);
      }
      this.stage.appendChild(node);
      this.later(1400, () => node.remove());
    }

    async reactToDeaths(ev, beforeState) {
      const sides = ["A", "B"];
      for (const side of sides) {
        const wasAlive = !beforeState || !beforeState[side] || beforeState[side].alive !== false;
        const nowAlive = ev.alive ? ev.alive[side] !== false : true;
        if (wasAlive && !nowAlive) {
          this.kill(side);
        }
      }
      if (sides.some((side) => !ev.alive || ev.alive[side] === false)) {
        await this.wait(this.ms(320));
      }
    }

    kill(side) {
      const unit = this.units[side];
      unit.classList.remove("attacking", "guarding", "dodging", "parrying", "countering", "ready");
      unit.classList.add("fallen");
      const mark = document.createElement("span");
      mark.className = "unit-mark";
      mark.textContent = "阵亡";
      unit.appendChild(mark);
      this.later(2100, () => mark.remove());
    }
  }

  window.BattleScene = Scene;
})();
