import XCTest

/// Walks every screen and keeps a screenshot of each, for looking at the app
/// without a phone (Scripts/sim-tour.sh). Needs a local server and a token:
/// the run passes it as TEST_RUNNER_JF_DEBUG_TOKEN.
final class TourTests: XCTestCase {
    private var app: XCUIApplication!

    override func setUp() {
        continueAfterFailure = true
        app = XCUIApplication()
        app.launchEnvironment["JF_DEBUG_TOKEN"] = ProcessInfo.processInfo.environment["JF_DEBUG_TOKEN"] ?? ""
        app.launch()
    }

    func testTour() {
        sleep(5)
        snap("01-overview")
        scroll(2, prefix: "01-overview")

        tab("Accounts")
        snap("02-accounts")
        scroll(2, prefix: "02-accounts")
        let firstAccount = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] '$'")).firstMatch
        if firstAccount.waitForExistence(timeout: 3) {
            firstAccount.tap()
            sleep(3)
            snap("03-account")
            scroll(2, prefix: "03-account")
            app.navigationBars.buttons.firstMatch.tap()
        }

        tab("Activity")
        snap("04-activity")
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] '$'")).firstMatch
        if row.waitForExistence(timeout: 3) {
            row.tap()
            sleep(2)
            snap("05-transaction")
            app.navigationBars.buttons.firstMatch.tap()
        }

        tab("Insights")
        for (i, name) in ["Cash flow", "Spending", "Subscriptions", "Net worth & debt", "Investing"].enumerated() {
            let b = app.buttons[name]
            if b.waitForExistence(timeout: 3) { b.tap() }
            sleep(4)
            snap("06-insights-\(i)")
            scroll(2, prefix: "06-insights-\(i)")
            app.swipeDown(); app.swipeDown(); app.swipeDown()
        }

        tab("Settings")
        snap("07-settings")

        tab("Overview")
        app.buttons["Blur numbers"].firstMatch.tap()
        sleep(1)
        snap("08-blur")
        app.buttons["Show numbers"].firstMatch.tap()
    }

    private func tab(_ name: String) {
        app.tabBars.buttons[name].tap()
        sleep(3)
    }

    private func scroll(_ times: Int, prefix: String) {
        for i in 1...times {
            app.swipeUp(velocity: .slow)
            sleep(2)
            snap("\(prefix)-\(i)")
        }
    }

    private func snap(_ name: String) {
        let a = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        a.name = name
        a.lifetime = .keepAlways
        add(a)
    }
}
