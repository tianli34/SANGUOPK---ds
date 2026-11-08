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
  const DEFENSE_VERB = { block: "格挡", parry: "卸力", dodge: "闪避", counter: "反击" };

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

      this.spawnDust();
      this.setSpeed(1);
    }

    spawnDust() {
      const dust = document.getElementById("dust");
      if (!dust) return;
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
      Object.keys(this.units).forEach((side) => {
        const alive = state && state[side] ? state[side].alive : true;
        if (!alive) {
          this.units[side].classList.add("fallen", "fallen-instant");
        }
      });
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

      this.slash(contact.x, contact.y, atk === "B");
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
        this.slash(contact.x, contact.y, def === "B");
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
      const baseX = side === "A" ? 29 : 71;
      node.style.left = `${baseX + (Math.random() * 5 - 2.5)}%`;
      node.style.top = `${44 - stack * 7}%`;
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
      arc.style.left = side === "A" ? "31%" : "69%";
      arc.style.top = "47%";
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
