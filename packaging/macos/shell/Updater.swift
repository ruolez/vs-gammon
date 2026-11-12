import AppKit
import CryptoKit

/// Checks GitHub Releases, then downloads a signed zip and swaps the bundle once the app has quit.
final class Updater {
    private struct Release { let version: String, zip: URL, signature: URL }
    enum Failure: Error { case moveToApplications, badSignature, badDownload }

    private var found: Release?
    static var currentVersion: String { Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0" }
    private static var feed: URL {
        URL(string: ProcessInfo.processInfo.environment["VSG_UPDATE_FEED"] ?? "https://api.github.com/repos/ruolez/vs-gammon/releases/latest")!
    }

    static func isNewer(_ candidate: String, than current: String) -> Bool {
        let parts = { (s: String) in s.split(separator: ".").map { Int($0) ?? 0 } }
        return parts(candidate).lexicographicallyPrecedes(parts(current)) == false && parts(candidate) != parts(current)
    }

    func check(completion: @escaping ([String: Any]?, String?) -> Void) {
        var request = URLRequest(url: Self.feed)
        request.setValue("VS-Gammon", forHTTPHeaderField: "User-Agent")
        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                if (response as? HTTPURLResponse)?.statusCode == 404 { return completion(["current": Self.currentVersion, "available": false], nil) }
                guard let data, let release = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let tag = release["tag_name"] as? String, let assets = release["assets"] as? [[String: Any]] else {
                    return completion(nil, error?.localizedDescription ?? "bad response")
                }
                let version = tag.hasPrefix("v") ? String(tag.dropFirst()) : tag
                func asset(_ name: String) -> URL? {
                    assets.first { ($0["name"] as? String) == name }.flatMap { ($0["browser_download_url"] as? String).flatMap(URL.init) }
                }
                let newer = Self.isNewer(version, than: Self.currentVersion)
                if newer, let zip = asset("VS-Gammon-\(version).zip"), let signature = asset("VS-Gammon-\(version).zip.sig") {
                    self.found = Release(version: version, zip: zip, signature: signature)
                    completion(["current": Self.currentVersion, "latest": version, "available": true], nil)
                } else {
                    completion(["current": Self.currentVersion, "available": false], nil)
                }
            }
        }.resume()
    }

    func install(completion: @escaping (Result<Void, Error>) -> Void) {
        guard let release = found else { return completion(.failure(Failure.badDownload)) }
        let target = Bundle.main.bundleURL
        guard !target.path.contains("/AppTranslocation/"), FileManager.default.isWritableFile(atPath: target.deletingLastPathComponent().path) else {
            return completion(.failure(Failure.moveToApplications))
        }
        DispatchQueue.global().async {
            let result = Result { try self.prepareAndSchedule(release, target: target) }
            DispatchQueue.main.async { completion(result) }
        }
    }

    private func fetch(_ url: URL) throws -> Data {
        let semaphore = DispatchSemaphore(value: 0)
        var body: Data?
        URLSession.shared.dataTask(with: url) { data, response, _ in
            if (response as? HTTPURLResponse)?.statusCode == 200 { body = data }
            semaphore.signal()
        }.resume()
        semaphore.wait()
        guard let body else { throw Failure.badDownload }
        return body
    }

    private func run(_ tool: String, _ arguments: [String]) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: tool)
        process.arguments = arguments
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else { throw Failure.badDownload }
    }

    private func prepareAndSchedule(_ release: Release, target: URL) throws {
        let zip = try fetch(release.zip)
        let signature = try fetch(release.signature)
        guard let encoded = Bundle.main.infoDictionary?["VSGUpdatePublicKey"] as? String, let raw = Data(base64Encoded: encoded),
              try Curve25519.Signing.PublicKey(rawRepresentation: raw).isValidSignature(signature, for: zip) else {
            throw Failure.badSignature
        }
        let work = FileManager.default.temporaryDirectory.appendingPathComponent("vs-gammon-update-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: work, withIntermediateDirectories: true)
        let archive = work.appendingPathComponent("update.zip")
        try zip.write(to: archive)
        try run("/usr/bin/ditto", ["-x", "-k", archive.path, work.path])
        let fresh = work.appendingPathComponent("VS Gammon.app")
        guard Bundle(url: fresh)?.infoDictionary?["CFBundleShortVersionString"] as? String == release.version else { throw Failure.badDownload }
        try run("/usr/bin/codesign", ["--verify", "--deep", "--strict", fresh.path])

        let swap = """
        while kill -0 "$1" 2>/dev/null; do sleep 0.1; done
        old="$2.old-$$"
        if mv "$2" "$old"; then
          if mv "$3" "$2"; then rm -rf "$old"; else mv "$old" "$2"; fi
        fi
        open "$2"
        rm -rf "$4"
        """
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/sh")
        process.arguments = ["-c", swap, "swap", String(ProcessInfo.processInfo.processIdentifier), target.path, fresh.path, work.path]
        try process.run()
    }
}
