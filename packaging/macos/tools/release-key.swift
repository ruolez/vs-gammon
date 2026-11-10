// Release signing for app updates. keygen: creates the key once. sign FILE: writes FILE.sig.
import CryptoKit
import Foundation

let directory = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".config/vs-gammon")
let keyFile = directory.appendingPathComponent("release.key")
let arguments = CommandLine.arguments

func die(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

switch arguments.dropFirst().first {
case "keygen":
    if FileManager.default.fileExists(atPath: keyFile.path) { die("\(keyFile.path) exists; never replace it, installed apps trust only that key") }
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    let key = Curve25519.Signing.PrivateKey()
    try Data(key.rawRepresentation.base64EncodedString().utf8).write(to: keyFile)
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: keyFile.path)
    print(key.publicKey.rawRepresentation.base64EncodedString())
case "sign":
    guard arguments.count == 3 else { die("usage: release-key sign FILE") }
    let encoded = try String(contentsOf: keyFile, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
    let key = try Curve25519.Signing.PrivateKey(rawRepresentation: Data(base64Encoded: encoded)!)
    let file = URL(fileURLWithPath: arguments[2])
    try key.signature(for: Data(contentsOf: file)).write(to: URL(fileURLWithPath: arguments[2] + ".sig"))
default:
    die("usage: release-key keygen | sign FILE")
}
