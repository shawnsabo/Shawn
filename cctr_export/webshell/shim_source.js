/* Tauri IPC 兼容 shim
 * 将前端对 window.__TAURI_INTERNALS__ 的调用桥接到本地 /api 命令通道。
 * 前端资产本身未做任何修改。 */
(function () {
  "use strict";

  var callbackSeq = 0;
  var callbacks = new Map();      // transformCallback id -> {cb, once}
  var listeners = new Map();      // eventId -> {event, handlerId}
  var eventHandlers = new Map();  // event -> Set(handlerId)
  var eventSeq = 0;

  function transformCallback(cb, once) {
    var id = ++callbackSeq;
    callbacks.set(id, { cb: cb, once: !!once });
    return id;
  }

  function invoke(cmd, args, opts) {
    if (cmd === "plugin:event|listen") {
      var ev = args && args.event;
      var handlerId = args && args.handler;
      if (!eventHandlers.has(ev)) eventHandlers.set(ev, new Set());
      eventHandlers.get(ev).add(handlerId);
      var eid = ++eventSeq;
      listeners.set(eid, { event: ev, handlerId: handlerId });
      return Promise.resolve(eid);
    }
    if (cmd === "plugin:event|unlisten") {
      var l = listeners.get(args && args.eventId);
      if (l) {
        var set = eventHandlers.get(l.event);
        if (set) set.delete(l.handlerId);
        listeners.delete(args.eventId);
      }
      return Promise.resolve(null);
    }
    if (cmd.indexOf("plugin:") === 0) {
      return Promise.resolve(null);
    }
    return fetch("/api/" + cmd, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(args || {})
    }).then(function (r) { return r.json(); }).then(function (out) {
      if (out && out.ok) return out.data;
      throw (out && out.error) || "未知错误";
    });
  }

  window.__TAURI_INTERNALS__ = {
    invoke: invoke,
    transformCallback: transformCallback,
    metadata: {
      currentWindow: { label: "main" },
      currentWebview: { windowLabel: "main", label: "main" }
    },
    plugins: {}
  };

  window.__TAURI_EVENT_PLUGIN_INTERNALS__ = {
    unregisterListener: function (event, eventId) {
      var l = listeners.get(eventId);
      if (l) {
        var set = eventHandlers.get(l.event);
        if (set) set.delete(l.handlerId);
        listeners.delete(eventId);
      }
    }
  };

  window.__tauri_shim__ = {
    emitEvent: function (event, payload) {
      var set = eventHandlers.get(event);
      if (!set) return;
      set.forEach(function (handlerId) {
        var entry = callbacks.get(handlerId);
        if (!entry) return;
        try {
          entry.cb({ event: event, id: handlerId, payload: payload });
        } catch (err) {
          console.error("[shim] event handler error:", err);
        }
        if (entry.once) callbacks.delete(handlerId);
      });
    }
  };
})();
