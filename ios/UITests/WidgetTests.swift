import XCTest

/// Adds the widgets to the simulator's Home Screen through the real gallery
/// and keeps screenshots (Scripts/sim-tour.sh <sim> <out> widgets). Signs the
/// app in first with the debug token so the widgets have something to show.
final class WidgetTests: XCTestCase {
    private let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")

    func testAddWidgets() {
        continueAfterFailure = true
        let app = XCUIApplication()
        app.launchEnvironment["JF_DEBUG_TOKEN"] = ProcessInfo.processInfo.environment["JF_DEBUG_TOKEN"] ?? ""
        app.launch()
        sleep(6)
        XCUIDevice.shared.press(.home)
        sleep(2)

        // Every preview in the gallery, in order: net worth S M L, this month
        // S M L, coming up S M L, account S, accounts M L.
        openGallery()
        for page in 0..<12 {
            snap("g-\(page)")
            springboard.swipeLeft()
            sleep(1)
        }
        closeGallery()

        // Then real ones, fed by the server through the shared Keychain.
        add(page: 2)   // net worth, large
        add(page: 11)  // accounts, large
        add(page: 10)  // accounts, medium
        add(page: 0)   // net worth, small
        let done = springboard.buttons["Done"]
        if done.waitForExistence(timeout: 2) { done.tap() }
        sleep(25)
        snap("home")
    }

    private func openGallery() {
        let edit = springboard.buttons["Edit"]
        if !edit.exists {
            springboard.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.8)).press(forDuration: 1.6)
            sleep(1)
        }
        if edit.waitForExistence(timeout: 3) {
            edit.tap()
            sleep(1)
        }
        let add = springboard.buttons.matching(NSPredicate(format: "label CONTAINS 'Add Widget'")).firstMatch
        if add.waitForExistence(timeout: 3) {
            add.tap()
            sleep(2)
        }
        let search = springboard.searchFields.firstMatch
        if search.waitForExistence(timeout: 3) {
            search.tap()
            let clear = springboard.buttons["Clear text"]
            if clear.exists { clear.tap() }
            search.typeText("jfinances")
            sleep(2)
        }
        // The first result sits just under the search field.
        springboard.coordinate(withNormalizedOffset: CGVector(dx: 0.3, dy: 0.29)).tap()
        sleep(2)
    }

    private func closeGallery() {
        let close = springboard.buttons["Close"]
        if close.waitForExistence(timeout: 2) { close.tap() }
        sleep(1)
    }

    private func add(page: Int) {
        openGallery()
        for _ in 0..<page {
            springboard.swipeLeft()
            sleep(1)
        }
        let add = springboard.buttons.matching(NSPredicate(format: "label CONTAINS 'Add Widget'")).firstMatch
        if add.waitForExistence(timeout: 3) {
            add.tap()
            sleep(2)
        } else {
            attach("tree-page-\(page)", springboard.debugDescription)
        }
    }

    private func snap(_ name: String) {
        let a = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        a.name = name
        a.lifetime = .keepAlways
        add(a)
    }

    private func attach(_ name: String, _ text: String) {
        let a = XCTAttachment(string: text)
        a.name = name
        a.lifetime = .keepAlways
        add(a)
    }
}
