// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "CheckoutBroadcast",
    platforms: [.iOS(.v15), .macOS(.v12)],
    products: [
        .library(name: "CheckoutBroadcast", targets: ["CheckoutBroadcast"]),
    ],
    targets: [
        .target(name: "CheckoutBroadcast"),
    ]
)
