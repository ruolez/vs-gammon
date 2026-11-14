import AppKit
import WebKit

/// With VSG_SELFTEST=<dir> set, drives the real web view through every page and menu, then quits.
/// Writes results.json and one PNG per step. Does nothing otherwise.
final class SelfTest {
    private struct Step { let path: String, lang: String, text: Int, theme: String, width: CGFloat }
    private let web: WebController
    private let dir: URL
    private var steps: [Step] = []
    private var results: [[String: Any]] = []
    private var onLoaded: (() -> Void)?
    private let playOnly = ProcessInfo.processInfo.environment["VSG_SELFTEST_PLAY"] != nil
    private var playStarted = false

    private static let probe = """
    JSON.stringify({path: location.pathname, shell: document.documentElement.dataset.shell, native: Native.available,
      lang: document.documentElement.lang, theme: document.documentElement.dataset.theme,
      root: getComputedStyle(document.documentElement).fontSize,
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      h1: (document.querySelector('h1') || {}).textContent, modal: typeof HTMLDialogElement.prototype.showModal,
      container: CSS.supports('container-type', 'inline-size'), font: document.fonts.check('16px Inter', 'Привет'),
      errors: window.__errors || []})
    """

    init?(web: WebController) {
        guard let path = ProcessInfo.processInfo.environment["VSG_SELFTEST"] else { return nil }
        self.web = web
        dir = URL(fileURLWithPath: path)
        let collector = "window.__errors=[];addEventListener('error',e=>__errors.push(e.message));addEventListener('unhandledrejection',e=>__errors.push(String(e.reason)))"
        web.webView.configuration.userContentController.addUserScript(WKUserScript(source: collector, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        let pages = ["/", "/practice", "/moves", "/matches", "/history", "/settings"]
        for width: CGFloat in [1320, 1024, 768, 480] {
            steps += pages.map { Step(path: $0, lang: "en", text: 100, theme: "light", width: width) }
            steps += pages.map { Step(path: $0, lang: "ru", text: 150, theme: "dark", width: width) }
        }
    }

    func pageDidLoad() {
        if let callback = onLoaded { onLoaded = nil; callback() } else { next() }
    }

    private func settle(_ work: @escaping () -> Void) { DispatchQueue.main.asyncAfter(deadline: .now() + 1.5, execute: work) }

    private func runUpdate() {
        let script = "(async()=>{const c=await Native.call('checkUpdate');const i=c.available?await Native.call('installUpdate'):null;return JSON.stringify({check:c,install:i})})()"
        web.webView.callAsyncJavaScript("return await \(script)", arguments: [:], in: nil, in: .page) { result in
            let text = (try? result.get()) as? String ?? "failed: \(result)"
            try? text.write(to: self.dir.appendingPathComponent("update.json"), atomically: true, encoding: .utf8)
            if !text.contains("\"ok\":true") { NSApp.terminate(nil) }
        }
    }

    private func next() {
        if ProcessInfo.processInfo.environment["VSG_SELFTEST_UPDATE"] != nil { return settle { self.runUpdate() } }
        if playOnly {
            if !playStarted { playStarted = true; testPlay() }
            return
        }
        guard !steps.isEmpty else { return testMenus() }
        let step = steps.removeFirst()
        web.webView.window?.setContentSize(NSSize(width: step.width, height: 800))
        let setup = "localStorage.setItem('ga-lang','\(step.lang)');localStorage.setItem('ga-text','\(step.text)');localStorage.setItem('ga-theme','\(step.theme)')"
        web.webView.evaluateJavaScript(setup) { _, _ in
            self.onLoaded = { self.settle { self.record(name: "\(step.lang)-\(Int(step.width))\(step.path.replacingOccurrences(of: "/", with: "-"))") { self.next() } } }
            self.web.load(step.path)
        }
    }

    private func record(name: String, then: @escaping () -> Void) {
        web.webView.evaluateJavaScript(Self.probe) { value, error in
            var entry: [String: Any] = ["step": name]
            if let text = value as? String, let data = text.data(using: .utf8), let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                entry.merge(object) { a, _ in a }
            } else {
                entry["probeError"] = error?.localizedDescription ?? "no value"
            }
            self.results.append(entry)
            self.web.webView.takeSnapshot(with: nil) { image, _ in
                if let image, let tiff = image.tiffRepresentation, let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) {
                    try? png.write(to: self.dir.appendingPathComponent("\(name).png"))
                }
                then()
            }
        }
    }

    private func find(_ key: String, in menu: NSMenu) -> (NSMenu, Int)? {
        for (index, item) in menu.items.enumerated() {
            if item.identifier?.rawValue == key { return (menu, index) }
            if let submenu = item.submenu, let found = find(key, in: submenu) { return found }
        }
        return nil
    }

    private func press(_ key: String) {
        guard let (menu, index) = find(key, in: NSApp.mainMenu!) else { return results.append(["step": "press \(key)", "missing": true]) }
        menu.performActionForItem(at: index)
    }

    private func menuTitles() -> [String] { NSApp.mainMenu!.items.map(\.title) }

    private func testMenus() {
        results.append(["step": "menu titles in Russian", "titles": menuTitles(), "badge": NSApp.dockTile.badgeLabel ?? ""])
        press("Actual Size")
        settle {
            self.record(name: "menu-actual-size") {
                self.press("Larger Text")
                self.settle {
                    self.record(name: "menu-larger-text") {
                        self.onLoaded = { self.settle { self.record(name: "menu-matches") { self.testInteractions() } } }
                        self.press("Matches")
                    }
                }
            }
        }
    }

    private func evaluate(_ name: String, _ body: String, then: @escaping () -> Void) {
        web.webView.callAsyncJavaScript(body, arguments: [:], in: nil, in: .page) { result in
            self.results.append(["step": name, "value": (try? result.get()) ?? "failed: \(result)"])
            then()
        }
    }

    private func testInteractions() {
        let sleep = "const sleep=ms=>new Promise(r=>setTimeout(r,ms));"
        evaluate("delete dialog opens and cancels", sleep + """
        const del=[...document.querySelectorAll('button')].find(b=>/Delete|Удалить/.test(b.title+(b.getAttribute('aria-label')||'')));del.click();await sleep(300);
        const d=document.querySelector('dialog[open]');const modal=d.matches(':modal');d.querySelector('[data-answer=no]').click();await sleep(200);
        return JSON.stringify({modal,closed:!document.querySelector('dialog[open]')});
        """) {
            self.onLoaded = {
                self.settle {
                    self.evaluate("keyboard move on the practice board", sleep + """
                    const undo=()=>[...document.querySelectorAll('button')].find(b=>/Undo|Отменить/.test(b.textContent));const before=undo().disabled;
                    const hit=document.querySelector('.hit[tabindex="0"]');hit.focus();
                    hit.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));await sleep(400);
                    if(undo().disabled){const again=document.querySelector('.hit[tabindex="0"]');again.focus();again.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));await sleep(400);}
                    return JSON.stringify({before,after:undo().disabled});
                    """) { self.finish() }
                }
            }
            self.web.load("/practice")
        }
    }

    // MARK: Play online (VSG_SELFTEST_PLAY=1: only this, leaves theme / language / text size alone)

    private func wait(_ seconds: Double, _ work: @escaping () -> Void) { DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: work) }

    private func recordPlay(_ name: String, then: @escaping () -> Void) {
        let probe = "JSON.stringify({path: location.pathname, host: !!Host, box: (b => b && {x: b.left, y: b.top, width: b.width, height: b.height})(document.getElementById('play-view')?.getBoundingClientRect()), input: document.getElementById('play-url')?.value, errors: window.__errors || []})"
        web.webView.evaluateJavaScript(probe) { value, _ in
            var entry: [String: Any] = ["step": name, "page": value as? String ?? "", "play": self.web.play.state,
                                        "playHidden": self.web.play.webView.isHidden, "playFrame": NSStringFromRect(self.web.play.webView.frame)]
            entry["window"] = NSStringFromRect(self.web.webView.window?.frame ?? .zero)
            self.web.play.webView.evaluateJavaScript("JSON.stringify({ready: document.readyState, text: (document.body?.innerText || '').slice(0, 200), ua: navigator.userAgent})") { site, error in
            entry["site"] = site as? String ?? "error: \(String(describing: error))"
            self.results.append(entry)
            self.web.play.webView.takeSnapshot(with: nil) { image, _ in
                if let image, let tiff = image.tiffRepresentation, let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) {
                    try? png.write(to: self.dir.appendingPathComponent("\(name)-site.png"))
                }
                self.web.webView.takeSnapshot(with: nil) { image, _ in
                    if let image, let tiff = image.tiffRepresentation, let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) {
                        try? png.write(to: self.dir.appendingPathComponent("\(name)-page.png"))
                    }
                    then()
                }
            }
            }
        }
    }

    /// Loads an app page and waits until it is the one showing (didFinish callbacks can belong to an earlier load).
    private func open(_ path: String, then: @escaping () -> Void) {
        web.load(path)
        func poll() {
            if web.webView.url?.path == path && !web.webView.isLoading { return wait(1.5, then) }
            wait(0.3, poll)
        }
        wait(0.3, poll)
    }

    private func js(_ script: String, then: @escaping (Any?) -> Void) { web.webView.evaluateJavaScript(script) { value, _ in then(value) } }

    /// VSG_SELFTEST_LIVE=<.mat>: imports the match, starts live stats against it in the Replay page inside the site view,
    /// lets the page's own capture loop read it for VSG_LIVE_SECONDS, then saves the live view and pictures.
    private func testLive(_ matPath: String) {
        let seconds = Double(ProcessInfo.processInfo.environment["VSG_LIVE_SECONDS"] ?? "") ?? 90
        let text = (try? String(contentsOfFile: matPath, encoding: .utf8)) ?? ""
        let setup = """
        const form = new FormData(); form.append('files', new Blob([mat], {type: 'text/plain'}), 'live-test.mat');
        const imported = await (await fetch('/api/matches', {method: 'POST', body: form})).json();
        const id = imported.results[0].id;
        if (!Prefs.get('live-open', false)) document.getElementById('live-toggle').click();
        await fetch('/api/live', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({opponent: 'ai', match_length: 3, player1: 'chessgamm0n', player2: 'fishsoup'})});
        document.dispatchEvent(new CustomEvent('playopen', {detail: location.origin + '/replay?match=' + id + '&ms=1400'}));
        return id;
        """
        open("/play") {
            self.web.webView.callAsyncJavaScript(setup, arguments: ["mat": text], in: nil, in: .page) { result in
                self.results.append(["step": "live setup", "value": (try? result.get()) ?? "failed: \(result)"])
                self.wait(seconds) {
                    self.web.webView.callAsyncJavaScript("return JSON.stringify(await (await fetch('/api/live')).json())", arguments: [:], in: nil, in: .page) { view in
                        if let json = (try? view.get()) as? String {
                            try? json.write(to: self.dir.appendingPathComponent("live.json"), atomically: true, encoding: .utf8)
                        }
                        self.recordPlay("live-end") {
                            self.web.webView.evaluateJavaScript("Prefs.set('live-open', false); fetch('/api/live', {method: 'DELETE'})") { _, _ in self.finishPlay() }
                        }
                    }
                }
            }
        }
    }

    private func testPlay() {
        if let mat = ProcessInfo.processInfo.environment["VSG_SELFTEST_LIVE"] { return testLive(mat) }
        let window = web.webView.window!
        let original = window.frame
        let site = ProcessInfo.processInfo.environment["VSG_PLAY_PROBE"]
        js("localStorage.getItem('ga-sidebar')") { sidebar in
            let restore = "localStorage.setItem('ga-sidebar', \((sidebar as? String).map { "'\($0)'" } ?? "''"))"
            self.js("localStorage.setItem('ga-sidebar','')") { _ in
                self.open("/play") {
                    if let site { self.web.play.webView.load(URLRequest(url: URL(string: site)!)) }
                    if let frames = Int(ProcessInfo.processInfo.environment["VSG_PLAY_FRAMES"] ?? "") {
                        return self.wait(8) { self.captureFrames(frames) { window.setFrame(original, display: true); self.js(restore) { _ in self.finishPlay() } } }
                    }
                    self.wait(10) {
                        self.recordPlay("play-open") {
                            window.setContentSize(NSSize(width: 900, height: 700))
                            self.wait(1.5) {
                                self.recordPlay("play-resized") {
                                    self.js("Shell.toggleCollapse()") { _ in
                                        self.wait(1.5) {
                                            self.recordPlay("play-rail") {
                                                self.js("Shell.toggleCollapse()") { _ in
                                                    self.open("/matches") {
                                                        self.recordPlay("play-left-for-matches") {
                                                            self.open("/play") {
                                                                self.recordPlay("play-back-again") {
                                                                    window.setFrame(original, display: true)
                                                                    self.js(restore) { _ in self.finishPlay() }
                                                                }
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    /// VSG_PLAY_FRAMES=n: saves n snapshots of the site, 0.7 s apart, through the same call the page uses.
    private func captureFrames(_ count: Int, index: Int = 0, then: @escaping () -> Void) {
        if index % 10 == 0 { results.append(["step": "frame \(index)", "play": web.play.state, "frame": NSStringFromRect(web.play.webView.frame), "hidden": web.play.webView.isHidden]) }
        guard index < count else { return then() }
        web.play.snapshot(width: 1000) { base64 in
            if let base64, let data = Data(base64Encoded: base64) {
                try? data.write(to: self.dir.appendingPathComponent(String(format: "frame-%03d.png", index)))
            }
            self.wait(0.7) { self.captureFrames(count, index: index + 1, then: then) }
        }
    }

    private func finishPlay() {
        if let data = try? JSONSerialization.data(withJSONObject: results, options: [.prettyPrinted]) {
            try? data.write(to: dir.appendingPathComponent("results.json"))
        }
        NSApp.terminate(nil)
    }

    private func finish() {
        web.webView.evaluateJavaScript("['ga-lang','ga-text','ga-theme'].forEach(k=>localStorage.removeItem(k))") { _, _ in
            if let data = try? JSONSerialization.data(withJSONObject: self.results, options: [.prettyPrinted]) {
                try? data.write(to: self.dir.appendingPathComponent("results.json"))
            }
            NSApp.terminate(nil)
        }
    }
}
