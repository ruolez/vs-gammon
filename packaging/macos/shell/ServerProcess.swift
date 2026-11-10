import Foundation

let serverBase = URL(string: "http://127.0.0.1:5565")!

/// Runs the bundled web server. It exits by itself when its stdin closes, so a crashed shell leaves nothing behind.
final class ServerProcess {
    private let process = Process()
    private let input = Pipe()
    private var stopping = false
    var onUnexpectedExit: (() -> Void)?

    static var logURL: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/VS Gammon.log")
    }

    func start() throws {
        let resources = Bundle.main.resourceURL!
        FileManager.default.createFile(atPath: Self.logURL.path, contents: nil)
        let log = try FileHandle(forWritingTo: Self.logURL)
        process.executableURL = resources.appendingPathComponent("python/bin/python3")
        process.arguments = ["-m", "app.desktop"]
        process.currentDirectoryURL = resources
        var env = ProcessInfo.processInfo.environment
        env["PYTHONHOME"] = resources.appendingPathComponent("python").path
        env["PYTHONPATH"] = resources.path
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        process.environment = env
        process.standardInput = input
        process.standardOutput = log
        process.standardError = log
        process.terminationHandler = { [weak self] _ in
            guard let self, !self.stopping else { return }
            DispatchQueue.main.async { self.onUnexpectedExit?() }
        }
        try process.run()
    }

    func stop() {
        stopping = true
        try? input.fileHandleForWriting.close()
        let deadline = Date().addingTimeInterval(2)
        while process.isRunning && Date() < deadline { usleep(20_000) }
        if process.isRunning { process.terminate() }
    }

    func waitUntilHealthy(timeout: TimeInterval, completion: @escaping (Bool) -> Void) {
        let deadline = Date().addingTimeInterval(timeout)
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 1
        let session = URLSession(configuration: config)
        func attempt() {
            session.dataTask(with: serverBase.appendingPathComponent("health")) { _, response, _ in
                let healthy = (response as? HTTPURLResponse)?.statusCode == 200
                if healthy || Date() > deadline || !self.process.isRunning {
                    DispatchQueue.main.async { completion(healthy) }
                } else {
                    DispatchQueue.global().asyncAfter(deadline: .now() + 0.05) { attempt() }
                }
            }.resume()
        }
        attempt()
    }
}
