import AppKit
import WebKit

/// Holds both web views; flipped so the page's CSS coordinates are the play view's frame as they are.
final class ContentView: NSView {
    override var isFlipped: Bool { true }
}

/// The game site on the Play online page: a second web view laid over the page's placeholder.
/// It outlives the page, so a game carries on while the user looks at other pages.
final class PlayController: NSObject, WKNavigationDelegate, WKUIDelegate {
    let webView: WKWebView
    var onState: (([String: Any]) -> Void)?
    private var observations: [NSKeyValueObservation] = []
    private var popups: [NSWindow] = []

    override init() {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        // Sites (and Google sign-in) refuse web views that don't say they are Safari.
        config.applicationNameForUserAgent = "Version/18.0 Safari/605.1.15"
        config.preferences.isElementFullscreenEnabled = true
        // Live stats keep reading the game while the window is behind others.
        if #available(macOS 14.0, *) { config.preferences.inactiveSchedulingPolicy = .none }
        webView = WKWebView(frame: .zero, configuration: config)
        super.init()
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.isHidden = true
        webView.wantsLayer = true
        webView.layer?.cornerRadius = 10
        webView.layer?.masksToBounds = true
        if #available(macOS 13.3, *) { webView.isInspectable = UserDefaults.standard.bool(forKey: "inspectable") }
        let report: (WKWebView, Any) -> Void = { [weak self] _, _ in self?.reportState() }
        observations = [
            webView.observe(\.url, changeHandler: report), webView.observe(\.title, changeHandler: report),
            webView.observe(\.isLoading, changeHandler: report), webView.observe(\.canGoBack, changeHandler: report),
            webView.observe(\.canGoForward, changeHandler: report),
        ]
    }

    var isShowing: Bool { !webView.isHidden }

    var state: [String: Any] {
        ["url": webView.url?.absoluteString ?? "", "title": webView.title ?? "", "loading": webView.isLoading,
         "canGoBack": webView.canGoBack, "canGoForward": webView.canGoForward]
    }

    private func reportState() { onState?(state) }

    /// Page → app: `{action: show|frame|hide|go|back|forward|reload|stop, url?, rect?}`; replies with the state.
    func handle(_ args: [String: Any]) -> [String: Any] {
        switch args["action"] as? String ?? "" {
        case "show":
            place(args["rect"])
            webView.isHidden = false
            if webView.url == nil, let url = webURL(args["url"]) { webView.load(URLRequest(url: url)) }
        case "frame":
            place(args["rect"])
        case "hide":
            hide()
        case "go":
            if let url = webURL(args["url"]) { webView.load(URLRequest(url: url)) }
        case "back": webView.goBack()
        case "forward": webView.goForward()
        case "reload": webView.reload()
        case "stop": webView.stopLoading()
        default: break
        }
        return state
    }

    /// The site as a PNG about `width` pixels wide (base64), for reading the board; nil while hidden or empty.
    func snapshot(width: Double, done: @escaping (String?) -> Void) {
        guard isShowing, webView.url != nil, webView.frame.width > 0 else { return done(nil) }
        let config = WKSnapshotConfiguration()
        let scale = webView.window?.backingScaleFactor ?? 2
        config.snapshotWidth = NSNumber(value: min(width / scale, webView.frame.width))
        webView.takeSnapshot(with: config) { image, _ in
            guard let cg = image?.cgImage(forProposedRect: nil, context: nil, hints: nil),
                  let png = NSBitmapImageRep(cgImage: cg).representation(using: .png, properties: [:]) else { return done(nil) }
            done(png.base64EncodedString())
        }
    }

    func hide() {
        if webView.window?.firstResponder === webView { webView.window?.makeFirstResponder(nil) }
        webView.isHidden = true
    }

    private func place(_ value: Any?) {
        guard let rect = value as? [String: Any], let x = rect["x"] as? Double, let y = rect["y"] as? Double,
              let width = rect["width"] as? Double, let height = rect["height"] as? Double else { return }
        webView.frame = NSRect(x: x, y: y, width: width, height: height)
    }

    private func webURL(_ value: Any?) -> URL? {
        guard let text = value as? String, let url = URL(string: text), ["http", "https"].contains(url.scheme ?? "") else { return nil }
        return url
    }

    // MARK: Navigation

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url, let scheme = url.scheme else { return decisionHandler(.cancel) }
        if ["http", "https", "about", "blob", "data"].contains(scheme) { return decisionHandler(.allow) }
        NSWorkspace.shared.open(url)
        decisionHandler(.cancel)
    }

    /// Sign-in windows (Google, Facebook) need a real popup that keeps `window.opener`.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        let width = windowFeatures.width?.doubleValue ?? 520, height = windowFeatures.height?.doubleValue ?? 680
        let popup = WKWebView(frame: NSRect(x: 0, y: 0, width: width, height: height), configuration: configuration)
        popup.navigationDelegate = self
        popup.uiDelegate = self
        let window = NSWindow(contentRect: popup.frame, styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = popup
        window.center()
        window.makeKeyAndOrderFront(nil)
        popups.append(window)
        let observation = popup.observe(\.title) { view, _ in window.title = view.title ?? "" }
        objc_setAssociatedObject(window, "titleObservation", observation, .OBJC_ASSOCIATION_RETAIN)
        return popup
    }

    func webViewDidClose(_ webView: WKWebView) {
        guard let window = popups.first(where: { $0.contentView === webView }) else { return }
        window.close()
        popups.removeAll { $0 === window }
    }

    // MARK: Dialogs the site may show (resign? leave the table?)

    private func sheet(_ webView: WKWebView, _ alert: NSAlert, _ done: @escaping (NSApplication.ModalResponse) -> Void) {
        guard let window = webView.window else { return done(alert.runModal()) }
        alert.beginSheetModal(for: window, completionHandler: done)
    }

    private func alert(_ message: String, _ frame: WKFrameInfo) -> NSAlert {
        let alert = NSAlert()
        alert.messageText = frame.request.url?.host ?? "VS Gammon"
        alert.informativeText = message
        return alert
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        sheet(webView, alert(message, frame)) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = alert(message, frame)
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        sheet(webView, alert) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let alert = alert(prompt, frame)
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 260, height: 24))
        field.stringValue = defaultText ?? ""
        alert.accessoryView = field
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        sheet(webView, alert) { completionHandler($0 == .alertFirstButtonReturn ? field.stringValue : nil) }
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        guard let window = webView.window else { return completionHandler(nil) }
        panel.beginSheetModal(for: window) { completionHandler($0 == .OK ? panel.urls : nil) }
    }
}
