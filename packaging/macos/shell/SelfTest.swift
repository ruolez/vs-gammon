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

    private func finish() {
        web.webView.evaluateJavaScript("['ga-lang','ga-text','ga-theme'].forEach(k=>localStorage.removeItem(k))") { _, _ in
            if let data = try? JSONSerialization.data(withJSONObject: self.results, options: [.prettyPrinted]) {
                try? data.write(to: self.dir.appendingPathComponent("results.json"))
            }
            NSApp.terminate(nil)
        }
    }
}
