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

        app.switches.firstMatch.tap()
        sleep(1)
        tab("Overview")
        snap("08-blur")
        tab("Settings")
        app.switches.firstMatch.tap()
    }

    /// The screens added to catch up with the dashboard: account details, market
    /// values, offline accounts, Activity's order and filter, Insights' money flow
    /// and the transactions behind a number.
    func testFeatures() {
        sleep(4)
        tab("Accounts")
        for (i, name) in ["Chase Mortgage", "Chase Sapphire", "Main house", "2022 Honda Odyssey", "Venmo", "Old 401(k)", "Ally High-Yield"].enumerated() {
            let row = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] %@", name)).firstMatch
            for _ in 0..<4 where !row.isHittable { app.swipeUp(velocity: .slow) }
            guard row.waitForExistence(timeout: 3) else { continue }
            row.tap()
            sleep(3)
            snap("10-account-\(i)")
            scroll(2, prefix: "10-account-\(i)")
            app.navigationBars.buttons.firstMatch.tap()
            sleep(1)
        }

        tab("Activity")
        let accounts = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'all accounts'")).firstMatch
        if accounts.waitForExistence(timeout: 3) {
            accounts.tap()
            sleep(1)
            snap("11-activity-accounts")
            let venmo = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'Venmo'")).firstMatch
            if venmo.waitForExistence(timeout: 2) { venmo.tap() } else { app.tap() }
            sleep(3)
            snap("11-activity-venmo")
            let picked = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'Venmo'")).firstMatch
            if picked.waitForExistence(timeout: 2) {
                picked.tap()
                app.buttons["All accounts"].firstMatch.tap()
                sleep(2)
            }
        }
        let order = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'newest first'")).firstMatch
        if order.waitForExistence(timeout: 3) {
            order.tap()
            let largest = app.buttons["Largest first"].firstMatch
            if largest.waitForExistence(timeout: 2) { largest.tap() }
            sleep(3)
            snap("11-activity-largest")
        }

        tab("Insights")
        app.buttons["Cash flow"].firstMatch.tap()
        sleep(4)
        app.swipeUp(velocity: .slow)
        sleep(2)
        snap("12-moneyflow")
        let source = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'deposit'")).firstMatch
        for _ in 0..<3 where !source.isHittable { app.swipeUp(velocity: .slow) }
        if source.waitForExistence(timeout: 3) {
            source.tap()
            sleep(3)
            snap("12-drill-income")
            app.navigationBars.buttons.firstMatch.tap()
            sleep(1)
        }
        app.swipeDown(); app.swipeDown(); app.swipeDown()
        app.buttons["Spending"].firstMatch.tap()
        sleep(4)
        snap("13-spending")
        let food = app.buttons.matching(NSPredicate(format: "label BEGINSWITH[c] 'food and drink'")).firstMatch
        if food.waitForExistence(timeout: 3) {
            food.tap()
            sleep(3)
            snap("13-drill-category")
            let largest = app.buttons["largest"].firstMatch
            if largest.waitForExistence(timeout: 2) { largest.tap(); sleep(3); snap("13-drill-largest") }
            app.navigationBars.buttons.firstMatch.tap()
            sleep(1)
        }
        let all = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Category'")).firstMatch
        if all.waitForExistence(timeout: 3) {
            all.tap()
            let pick = app.buttons["food and drink"].firstMatch
            if pick.waitForExistence(timeout: 2) { pick.tap() }
            sleep(4)
            snap("13-spending-food")
            scroll(2, prefix: "13-spending-food")
        }
        app.swipeDown(); app.swipeDown(); app.swipeDown()
        app.buttons["Net worth & debt"].firstMatch.tap()
        sleep(4)
        scroll(3, prefix: "14-wealth")
        app.swipeDown(); app.swipeDown(); app.swipeDown(); app.swipeDown()
        app.buttons["Investing"].firstMatch.tap()
        sleep(4)
        scroll(2, prefix: "15-investing")
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
