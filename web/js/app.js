/*
 * 文件名: app.js
 * 用途: 网页入口 —— 加载战斗事件、同步面板与战报、控制播放与回退
 *
 * 所有 HP / SP / 胆气 / 伤害均来自事件 JSON 的状态快照与差值，
 * 前端不做任何命中或伤害计算。
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (value) =>
    String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[ch]));

  const TIER_CLASSES = ["tier-0", "tier-1", "tier-2", "tier-3"];

  const S = {
    doc: null,
    events: [],
    warriors: null,
    initial: null,
    cursor: -1,
    playing: false,
    paused: false,
    speed: 1,
    token: 0,
    log: null,
    scene: null,
    lastRound: null,
  };

  const els = {
    stage: $("stage"),
    roundLabel: $("round-label"),
    tickLabel: $("tick-label"),
    actionRound: $("action-round"),
    actionText: $("action-text"),
    hpLead: $("hp-lead"),
    spLead: $("sp-lead"),
    progress: $("progress"),
    eventCounter: $("event-counter"),
    logList: $("log-list"),
    logNote: $("log-note"),
    logPanel: $("log-panel"),
    leadReport: $("lead-report"),
    leadReportGrid: $("lead-report-grid"),
    resultOverlay: $("result-overlay"),
    resultTitle: $("result-title"),
    resultSub: $("result-sub"),
    resultStats: $("result-stats"),
    emptyState: $("empty-state"),
    btnStart: $("btn-start"),
    btnPause: $("btn-pause"),
    btnPrev: $("btn-prev"),
    btnReplay: $("btn-replay"),
    btnEnd: $("btn-end"),
  };

  /* ================= 顶部状态面板 ================= */

  const Hud = {
    init(doc) {
      this.doc = doc;
      this.warriors = doc.warriors;
      this.prevTier = { A: { hp: null, sp: null }, B: { hp: null, sp: null } };
      this.courageTimers = { A: null, B: null };
      this.leaderText = { hp: null, sp: null };

      ["A", "B"].forEach((side) => {
        const warrior = doc.warriors[side];
        $("name-" + side).textContent = warrior.name;
        const skillEl = $("skill-" + side);
        const skill = warrior.skills && warrior.skills.length ? warrior.skills[0] : "";
        if (skill) {
          const short = skill.split("（")[0];
          skillEl.textContent = `特技 · ${short}`;
          skillEl.title = skill;
          skillEl.hidden = false;
        } else {
          skillEl.hidden = true;
        }

        const weaponEl = $("weapon-" + side);
        const weapon = warrior.weapon;
        if (weapon && weapon.name) {
          weaponEl.textContent = `兵器 · ${weapon.name}`;
          weaponEl.title = weapon.categoryLabel || "";
          weaponEl.hidden = false;
        } else {
          weaponEl.hidden = true;
        }
      });

      this.apply(initialState(doc), { instant: true });
    },

    apply(state, options = {}) {
      const instant = Boolean(options.instant);
      const effects = options.effects || null;
      const flash = !instant && options.flash !== false;

      ["A", "B"].forEach((side) => {
        const warrior = this.warriors[side];
        const current = state[side];
        const hpPct = clamp(current.hp / warrior.hpMax, 0, 1);
        const spPct = clamp(current.sp / warrior.spMax, 0, 1);

        this.setGauge(side, "hp", current.hp, warrior.hpMax, hpPct, flash);
        this.setGauge(side, "sp", current.sp, warrior.spMax, spPct, flash);

        $("courage-" + side).textContent = String(current.courage);

        if (effects && effects[side]) {
          const delta = effects[side].courage;
          if (delta && Math.abs(delta) >= 10) this.showCourageTip(side, delta);
        }
      });

      this.renderLeaders(state, !instant);
    },

    setGauge(side, stat, value, max, pct, flash) {
      const gauge = $(`${stat}-gauge-${side}`);
      const fill = gauge.querySelector(".gauge-fill");
      const valueEl = $(`${stat}-value-${side}`);
      const label = stat === "hp" ? "HP" : "SP";

      fill.style.width = `${(pct * 100).toFixed(2)}%`;
      valueEl.textContent = String(Math.round(value));
      gauge.title = `${label} ${Math.round(value)} / ${Math.round(max)}（${(pct * 100).toFixed(1)}%）`;

      const tier = pct >= 0.75 ? 0 : pct >= 0.5 ? 1 : pct >= 0.25 ? 2 : 3;
      gauge.classList.remove(...TIER_CLASSES);
      gauge.classList.add(`tier-${tier}`);

      const prev = this.prevTier[side][stat];
      if (flash && prev !== null && tier > prev) {
        const track = gauge.querySelector(".gauge-track");
        const seq = (gauge._flashSeq = (gauge._flashSeq || 0) + 1);
        gauge.classList.remove("tier-flash");
        void gauge.offsetWidth;
        gauge.classList.add("tier-flash");
        const clear = (event) => {
          if (event.target !== track || event.animationName !== "tier-flash") return;
          gauge.removeEventListener("animationend", clear);
          if (gauge._flashSeq === seq) gauge.classList.remove("tier-flash");
        };
        gauge.addEventListener("animationend", clear);
      }
      this.prevTier[side][stat] = tier;
    },

    showCourageTip(side, delta) {
      const el = $("courage-caption-" + side);
      el.textContent = `胆气 ${delta > 0 ? "+" : ""}${delta}`;
      el.classList.remove("is-up", "is-down");
      el.classList.add(delta > 0 ? "is-up" : "is-down");
      window.clearTimeout(this.courageTimers[side]);
      this.courageTimers[side] = window.setTimeout(() => {
        el.classList.remove("is-up", "is-down");
      }, 1400);
    },

    renderLeaders(state, animate) {
      const a = this.warriors.A;
      const b = this.warriors.B;
      const hpA = (state.A.hp / a.hpMax) * 100;
      const hpB = (state.B.hp / b.hpMax) * 100;
      const spA = (state.A.sp / a.spMax) * 100;
      const spB = (state.B.sp / b.spMax) * 100;

      const lines = {
        hp: leaderLine("HP", a.name, hpA, b.name, hpB),
        sp: leaderLine("SP", a.name, spA, b.name, spB),
      };

      [["hp", els.hpLead], ["sp", els.spLead]].forEach(([key, el]) => {
        if (this.leaderText[key] === lines[key].html) return;
        const previous = this.leaderText[key];
        this.leaderText[key] = lines[key].html;
        el.innerHTML = lines[key].html;
        if (animate && previous !== null) {
          el.classList.remove("lead-changed");
          void el.offsetWidth;
          el.classList.add("lead-changed");
        }
      });
    },
  };

  function leaderLine(label, nameA, pctA, nameB, pctB) {
    const diff = pctA - pctB;
    if (Math.abs(diff) < 0.0001) {
      return {
        html: `${label} 持平 <span class="lead-pct">（${nameA} ${pctA.toFixed(1)}% / ${nameB} ${pctB.toFixed(1)}%）</span>`,
      };
    }
    const leader = diff > 0 ? nameA : nameB;
    const gap = Math.abs(diff).toFixed(1);
    return {
      html: `${label} 领先 · <b>${esc(leader)}</b> +${gap} 个百分点 <span class="lead-pct">（${nameA} ${pctA.toFixed(1)}% / ${nameB} ${pctB.toFixed(1)}%）</span>`,
    };
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function initialState(doc) {
    const make = (side) => {
      const warrior = doc.warriors[side];
      return {
        name: warrior.name,
        hp: warrior.hp,
        sp: warrior.sp,
        courage: warrior.courage,
        alive: true,
      };
    };
    return { A: make("A"), B: make("B") };
  }

  function renderLeadReport(doc) {
    const records = doc.battle && doc.battle.leadRecords;
    if (!records) return;
    const names = { A: doc.warriors.A.name, B: doc.warriors.B.name };

    els.leadReportGrid.innerHTML = ["hp", "sp"].map((key) => {
      const section = records[key];
      if (!section) return "";
      const rows = (section.changes || [])
        .map((change) => {
          const name = change.name || names[change.side] || "";
          return `<tr><td>第 ${esc(change.round)} 回合</td><td>${esc(name)}领先</td></tr>`;
        })
        .join("");
      const longest = section.longest || { A: 0, B: 0 };
      const maxGap = section.maxGap || { A: 0, B: 0 };
      return `<section class="lead-col">
        <h4>${key.toUpperCase()}</h4>
        ${rows ? `<table class="lead-table"><tbody>${rows}</tbody></table>` : `<p class="lead-empty">全程持平</p>`}
        <ul class="lead-metrics">
          <li>最长持续领先：<b>${esc(names.A)}</b> ${longest.A} 回合 · <b>${esc(names.B)}</b> ${longest.B} 回合</li>
          <li>最大领先幅度：<b>${esc(names.A)}</b> ${(maxGap.A * 100).toFixed(1)}% · <b>${esc(names.B)}</b> ${(maxGap.B * 100).toFixed(1)}%</li>
        </ul>
      </section>`;
    }).join("");
  }

  function showLeadReport(visible) {
    if (!els.leadReport) return;
    els.leadReport.hidden = !visible || !els.leadReportGrid.innerHTML;
  }

  /* ================= 战报 ================= */

  class LogView {
    constructor() {
      this.list = els.logList;
      this.note = els.logNote;
      this.logged = -1;
      this.round = 0;
      this.currentEl = null;
      this.total = 0;
    }

    clear() {
      this.list.innerHTML = "";
      this.logged = -1;
      this.round = 0;
      this.currentEl = null;
      this.note.textContent = "按事件回放 · 可前后拖动";
    }

    rebuild(events, upto, total) {
      this.total = total;
      this.clear();
      for (let i = 0; i <= upto; i += 1) {
        this.add(events[i], i, true);
      }
      this.scrollToEnd();
    }

    ensureRound(ev) {
      if (!ev.round || ev.round === this.round) return;
      this.round = ev.round;
      const head = document.createElement("li");
      head.className = "log-round-head";
      head.textContent = `第 ${ev.round} 回合`;
      this.list.appendChild(head);
    }

    add(ev, index, silent) {
      if (index <= this.logged) return;
      this.ensureRound(ev);
      this.logged = index;

      if (ev.type === "round_end") return;

      const li = document.createElement("li");
      li.dataset.index = String(index);

      if (ev.type === "battle_start") {
        li.className = "log-entry is-start";
        li.innerHTML = "战鼓擂响，两将出阵";
      } else if (ev.type === "skill_trigger") {
        li.className = "log-entry";
        const skill = ev.skill || {};
        li.innerHTML = `<span class="log-skill">✦ 特技 · ${esc(skill.name || "")}</span>
          <span class="log-owner">${esc(skill.warrior || "")}</span>
          ${skill.amount ? `<span class="log-effects"><span class="fx-courage-up">AP +${esc(skill.amount)}</span></span>` : ""}`;
      } else if (ev.type === "attack") {
        li.className = "log-entry";
        const defense = ev.defense || {};
        const fx = [];
        ["A", "B"].forEach((side) => {
          const tags = effectTags(ev, side);
          if (tags) {
            const name = side === "A" ? S.warriors.A.name : S.warriors.B.name;
            fx.push(`<span class="log-owner">${esc(name)}</span>${tags}`);
          }
        });
        const dead = deadNames(ev);
        if (dead.length) li.classList.add("is-death");
        li.innerHTML =
          `<span class="log-actor">${esc(ev.actor.name)}</span>进攻 → <span class="log-defender">${esc(ev.defender.name)}</span>` +
          `<span class="def-word">${esc(defense.label || "")}</span>` +
          `<span class="def-result ${defense.success ? "is-success" : "is-fail"}">${defense.success ? "成功" : "失败"}</span>` +
          (fx.length ? `<span class="log-effects">${fx.join(" · ")}</span>` : "") +
          (dead.length ? `<span class="log-death">☠ ${dead.map(esc).join(" / ")} 阵亡</span>` : "");
      } else if (ev.type === "clash") {
        li.className = "log-entry";
        const participants = (ev.clash && ev.clash.participants) || [];
        const fx = [];
        ["A", "B"].forEach((side) => {
          const tags = effectTags(ev, side);
          if (tags) {
            fx.push(`<span class="log-owner">${esc(S.warriors[side].name)}</span>${tags}`);
          }
        });
        li.innerHTML =
          `<span class="log-clash">⚔ 拼刀</span>` +
          `<span class="log-owner">${participants.map(esc).join(" / ")}</span>` +
          (fx.length ? `<span class="log-effects">${fx.join(" · ")}</span>` : "");
      } else if (ev.type === "sp_leader_change") {
        li.className = "log-entry is-meta";
        const leader = ev.leader && S.warriors[ev.leader] ? S.warriors[ev.leader].name : "";
        li.textContent = leader ? `体力领先 → ${leader}` : "体力领先易主";
      } else if (ev.type === "battle_end" || ev.type === "timeout") {
        li.className = "log-entry is-result";
        li.textContent = ev.text;
      } else {
        return;
      }

      this.list.appendChild(li);
      if (this.currentEl) this.currentEl.classList.remove("current");
      li.classList.add("current");
      this.currentEl = li;
      if (this.total) {
        this.note.textContent = `事件 ${index + 1} / ${this.total}${ev.round ? ` · 第 ${ev.round} 回合` : ""}`;
      }
      if (!silent) this.scrollToEnd();
    }

    scrollToEnd() {
      window.requestAnimationFrame(() => {
        this.list.scrollTop = this.list.scrollHeight;
      });
    }
  }

  function effectTags(ev, side) {
    const fx = ev.effects && ev.effects[side];
    if (!fx) return "";
    const tags = [];
    if (fx.hp <= -0.5) tags.push(`<span class="fx-hp">HP ${Math.round(fx.hp)}</span>`);
    if (fx.sp <= -0.4) tags.push(`<span class="fx-sp">SP ${Math.round(fx.sp)}</span>`);
    else if (fx.sp >= 0.4) tags.push(`<span class="fx-sp">SP +${Math.round(fx.sp)}</span>`);
    if (fx.courage) {
      const cls = fx.courage > 0 ? "fx-courage-up" : "fx-courage-down";
      tags.push(`<span class="${cls}">胆气 ${fx.courage > 0 ? "+" : ""}${fx.courage}</span>`);
    }
    return tags.join(" ");
  }

  function deadNames(ev) {
    if (!ev.alive) return [];
    const names = [];
    if (ev.alive.A === false) names.push(S.warriors.A.name);
    if (ev.alive.B === false) names.push(S.warriors.B.name);
    return names;
  }

  /* ================= 播放控制 ================= */

  function updatePosition(index) {
    const total = S.events.length;
    const max = Math.max(0, total - 1);
    const clamped = Math.max(0, index);
    els.progress.value = String(clamped);
    els.progress.style.setProperty("--progress", `${max > 0 ? (clamped / max) * 100 : 0}%`);
    els.eventCounter.textContent = index < 0 ? `0 / ${total}` : `${index + 1} / ${total}`;
  }

  function setRoundTick(ev, instant) {
    const round = ev && ev.round ? ev.round : 1;
    const tick = ev ? ev.tick : 0;
    els.roundLabel.textContent = `第 ${round} 回合`;
    els.tickLabel.textContent = `tick ${tick}`;
    els.actionRound.textContent = `第 ${round} 回合`;
    if (!instant && S.lastRound !== round) {
      els.roundLabel.classList.remove("pop");
      void els.roundLabel.offsetWidth;
      els.roundLabel.classList.add("pop");
    }
    S.lastRound = round;
  }

  function formatAction(ev) {
    if (!ev) return "战斗即将开始";
    if (ev.type === "attack") {
      const defense = ev.defense || {};
      return (
        `${esc(ev.actor.name)}进攻 → ${esc(ev.defender.name)}` +
        `<span class="def-inline">${esc(defense.label || "")}</span>` +
        `<span class="${defense.success ? "def-ok" : "def-bad"}">${defense.success ? "成功" : "失败"}</span>`
      );
    }
    if (ev.type === "clash") {
      return `拼刀！${(ev.clash && ev.clash.participants ? ev.clash.participants : []).map(esc).join(" / ")}`;
    }
    return esc(ev.text);
  }

  function setAction(ev) {
    els.actionText.innerHTML = formatAction(ev);
  }

  function updateButtons() {
    els.btnStart.disabled = S.playing;
    els.btnStart.textContent = "开始";
    els.btnPause.disabled = !S.playing;
    els.btnPause.textContent = S.paused ? "继续" : "暂停";
    els.btnPrev.disabled = S.cursor <= -1;
  }

  function showResult(ev) {
    const battle = S.doc.battle;
    const finalState = ev && ev.state ? ev.state : S.initial;
    const winner = battle.winnerSide;
    els.resultTitle.textContent = winner && S.warriors[winner] ? `${S.warriors[winner].name} 胜` : "平局";
    els.resultSub.textContent = `${
      battle.outcome === "timeout" ? "超时判定 · " : ""
    }共 ${battle.rounds} 回合 · ${battle.ticks} tick`;
    els.resultStats.innerHTML = ["A", "B"]
      .map((side) => {
        const warrior = S.warriors[side];
        const state = finalState[side];
        return `<span>${esc(warrior.name)}<b>HP ${Math.round(state.hp)} · SP ${Math.round(state.sp)}</b></span>`;
      })
      .join("");
    els.resultOverlay.hidden = false;
    showLeadReport(true);
  }

  function hideResult() {
    els.resultOverlay.hidden = true;
    showLeadReport(false);
  }

  function seekTo(index) {
    if (!S.events.length) return;
    S.token += 1;
    S.playing = false;
    S.paused = false;
    S.scene.setPaused(false);

    const last = S.events.length - 1;
    const target = clamp(index, -1, last);
    S.cursor = target;

    const state = target < 0 ? S.initial : S.events[target].state;
    S.scene.restore(state);
    Hud.apply(state, { instant: true });

    if (target < 0) {
      S.log.total = S.events.length;
      S.log.clear();
      setRoundTick(null, true);
      setAction(null);
      hideResult();
      updatePosition(-1);
    } else {
      const ev = S.events[target];
      S.log.rebuild(S.events, target, S.events.length);
      setRoundTick(ev, true);
      setAction(ev);
      updatePosition(target);
      if (target === last) showResult(ev);
      else hideResult();
    }

    updateButtons();
  }

  async function waitForResume(token) {
    return new Promise((resolve) => {
      const check = () => {
        if (token !== S.token) return resolve(false);
        if (!S.paused) return resolve(true);
        window.setTimeout(check, 60);
      };
      check();
    });
  }

  async function startPlayback(fromIndex) {
    if (!S.events.length) return;
    const token = ++S.token;
    S.playing = true;
    S.paused = false;
    S.scene.setPaused(false);
    updateButtons();

    for (let i = Math.max(0, fromIndex); i < S.events.length; i += 1) {
      if (token !== S.token) return;
      if (S.paused) {
        const ok = await waitForResume(token);
        if (!ok || token !== S.token) return;
      }

      const ev = S.events[i];
      const before = i === 0 ? S.initial : S.events[i - 1].state;
      S.cursor = i;

      updatePosition(i);
      S.log.total = S.events.length;
      S.log.add(ev, i);
      setAction(ev);
      setRoundTick(ev, false);

      await S.scene.animateEvent(ev, before, () => {
        if (token !== S.token) return;
        Hud.apply(ev.state, { effects: ev.effects });
      });
      if (token !== S.token) return;

      if (ev.type !== "attack" && ev.type !== "clash") {
        Hud.apply(ev.state, { effects: ev.effects });
      }

      if (ev.type === "battle_end") {
        showResult(ev);
      }

      if (i === S.events.length - 1) {
        if (ev.type !== "battle_end" && ev.type !== "timeout") showResult(ev);
        finishPlayback(token);
        return;
      }

      const next = S.events[i + 1];
      const gap = Math.max(30, Math.min(160, (next.tick - ev.tick) * 1.2)) / S.speed;
      await S.scene.wait(gap);
      if (token !== S.token) return;
    }
    finishPlayback(token);
  }

  function finishPlayback(token) {
    if (token !== undefined && token !== S.token) return;
    S.playing = false;
    S.paused = false;
    S.scene.setPaused(false);
    updateButtons();
  }

  function replay() {
    seekTo(-1);
    window.setTimeout(() => startPlayback(0), 220);
  }

  function startOrResume() {
    if (S.playing) {
      if (S.paused) {
        S.paused = false;
        S.scene.setPaused(false);
        updateButtons();
      }
      return;
    }
    if (S.cursor >= S.events.length - 1) {
      replay();
      return;
    }
    startPlayback(S.cursor + 1);
  }

  function togglePause() {
    if (!S.playing) return;
    S.paused = !S.paused;
    S.scene.setPaused(S.paused);
    updateButtons();
  }

  /* ================= 初始化 ================= */

  async function loadBattle() {
    try {
      const response = await fetch("data/battle.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      if (window.BATTLE_DATA) return window.BATTLE_DATA;
      throw error;
    }
  }

  function bindControls() {
    els.btnStart.addEventListener("click", startOrResume);
    els.btnPause.addEventListener("click", togglePause);
    els.btnReplay.addEventListener("click", replay);
    els.btnPrev.addEventListener("click", () => seekTo(S.cursor - 1));
    els.btnEnd.addEventListener("click", () => seekTo(S.events.length - 1));
    $("btn-result-replay").addEventListener("click", replay);

    document.querySelectorAll(".speed-btn").forEach((button) => {
      button.addEventListener("click", () => {
        S.speed = Number(button.dataset.speed) || 1;
        S.scene.setSpeed(S.speed);
        document.querySelectorAll(".speed-btn").forEach((item) => {
          item.classList.toggle("is-active", item === button);
        });
        updateButtons();
      });
    });

    els.progress.addEventListener("input", () => {
      seekTo(Number(els.progress.value));
    });

    $("btn-log-toggle").addEventListener("click", (event) => {
      const collapsed = els.logPanel.classList.toggle("is-collapsed");
      event.currentTarget.textContent = collapsed ? "展开" : "收起";
    });

    document.addEventListener("keydown", (event) => {
      if (event.target && event.target.tagName === "INPUT") return;
      if (event.key === " ") {
        event.preventDefault();
        if (S.playing) togglePause();
        else startOrResume();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        seekTo(S.cursor - 1);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        seekTo(S.cursor + 1);
      }
    });
  }

  async function boot() {
    let doc;
    try {
      doc = await loadBattle();
    } catch (error) {
      console.error("加载战斗数据失败:", error);
      els.emptyState.hidden = false;
      return;
    }

    if (!doc || !Array.isArray(doc.events) || !doc.events.length || !doc.warriors) {
      els.emptyState.hidden = false;
      return;
    }

    S.doc = doc;
    S.events = doc.events;
    S.warriors = doc.warriors;
    S.initial = initialState(doc);

    S.scene = new window.BattleScene();
    S.scene.init(doc);
    Hud.init(doc);
    S.log = new LogView();
    renderLeadReport(doc);

    els.progress.max = String(Math.max(0, S.events.length - 1));
    els.progress.value = "0";
    bindControls();
    seekTo(-1);

    window.setTimeout(() => {
      if (S.cursor === -1) startPlayback(0);
    }, 700);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
