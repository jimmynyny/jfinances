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
        // This month's numbers open their transactions: a category, then money in.
        app.swipeDown(); app.swipeDown()
        let category = app.buttons.matching(NSPredicate(format: "label CONTAINS '%'")).firstMatch
        if category.waitForExistence(timeout: 3) {
            if !category.isHittable { app.swipeUp() }
            category.tap()
            sleep(3)
            snap("01-overview-category")
            app.navigationBars.buttons.firstMatch.tap()
            sleep(1)
        }
        let moneyIn = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'money in'")).firstMatch
        if moneyIn.waitForExistence(timeout: 3) {
            if !moneyIn.isHittable { app.swipeUp() }
            moneyIn.tap()
            sleep(3)
            snap("01-overview-money-in")
            app.navigationBars.buttons.firstMatch.tap()
            sleep(1)
        }

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

    /// Editing from the phone: an account's Edit menu and its sheets, a loan's
    /// details form, a transaction's edit sheet, a subscription's verdict menu,
    /// an alert's dismiss menu, and Settings → Connections.
    func testEditing() {
        sleep(4)
        tab("Accounts")
        let mortgage = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'Chase Mortgage'")).firstMatch
        for _ in 0..<4 where !mortgage.isHittable { app.swipeUp(velocity: .slow) }
        if mortgage.waitForExistence(timeout: 3) {
            mortgage.tap()
            sleep(3)
            app.navigationBars.buttons["Edit"].firstMatch.tap()
            sleep(1)
            snap("20-account-menu")
            app.buttons["Edit account…"].firstMatch.tap()
            sleep(2)
            snap("21-account-edit")
            app.buttons["Cancel"].firstMatch.tap()
            sleep(1)
            let add = app.buttons.matching(NSPredicate(format: "label BEGINSWITH[c] 'Add details' OR label BEGINSWITH[c] 'Edit details'")).firstMatch
            for _ in 0..<4 where !add.isHittable { app.swipeUp(velocity: .slow) }
            if add.waitForExistence(timeout: 3) {
                add.tap()
                sleep(3)
                snap("22-terms")
                scroll(1, prefix: "22-terms")
                app.buttons["Cancel"].firstMatch.tap()
                sleep(1)
            }
            app.navigationBars.buttons.firstMatch.tap()
            sleep(1)
        }
        app.swipeDown(); app.swipeDown(); app.swipeDown()
        let house = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'Main house'")).firstMatch
        for _ in 0..<4 where !house.isHittable { app.swipeUp(velocity: .slow) }
        if house.waitForExistence(timeout: 3) {
            house.tap()
            sleep(3)
            app.navigationBars.buttons["Edit"].firstMatch.tap()
            sleep(1)
            app.buttons["Update value…"].firstMatch.tap()
            sleep(2)
            snap("23-value")
            app.buttons["Cancel"].firstMatch.tap()
            sleep(1)
            let mv = app.buttons.matching(NSPredicate(format: "label == 'Edit' OR label == 'Add details'")).element(boundBy: 1)
            if mv.waitForExistence(timeout: 3) {
                mv.tap()
                sleep(2)
                snap("24-asset")
                app.buttons["Cancel"].firstMatch.tap()
                sleep(1)
            }
            app.navigationBars.buttons.firstMatch.tap()
            sleep(1)
        }
        app.swipeDown(); app.swipeDown(); app.swipeDown()
        let addOffline = app.buttons["Add an offline account"].firstMatch
        for _ in 0..<6 where !addOffline.isHittable { app.swipeUp(velocity: .slow) }
        if addOffline.waitForExistence(timeout: 3) {
            addOffline.tap()
            sleep(2)
            snap("25-add-offline")
            app.buttons["vehicle"].firstMatch.tap()
            sleep(1)
            snap("25-add-offline-vehicle")
            app.buttons["Cancel"].firstMatch.tap()
            sleep(1)
        }

        tab("Activity")
        let row = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] '$'")).firstMatch
        if row.waitForExistence(timeout: 3) {
            row.tap()
            sleep(2)
            app.navigationBars.buttons["Edit"].firstMatch.tap()
            sleep(2)
            snap("26-txn-edit")
            app.buttons["Cancel"].firstMatch.tap()
            sleep(1)
            app.navigationBars.buttons.firstMatch.tap()
        }

        tab("Insights")
        app.buttons["Subscriptions"].firstMatch.tap()
        sleep(4)
        snap("27-subscriptions")
        let stream = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'next'")).firstMatch
        if stream.waitForExistence(timeout: 3) {
            stream.tap()
            sleep(1)
            snap("27-subscription-menu")
            app.buttons["Rename…"].firstMatch.tap()
            sleep(2)
            snap("27-rename")
            app.buttons["Cancel"].firstMatch.tap()
            sleep(1)
        }
        let alert = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'usual' OR label CONTAINS[c] 'Price went' OR label CONTAINS[c] 'twice'")).firstMatch
        for _ in 0..<4 where !alert.isHittable { app.swipeUp(velocity: .slow) }
        if alert.waitForExistence(timeout: 3) {
            alert.tap()
            sleep(1)
            snap("28-alert-menu")
            app.tap()
        }

        tab("Settings")
        let connections = app.buttons.matching(NSPredicate(format: "label BEGINSWITH[c] 'Connections'")).firstMatch
        if connections.waitForExistence(timeout: 3) {
            connections.tap()
            sleep(4)
            snap("29-connections")
            scroll(1, prefix: "29-connections")
        }
    }

    /// Settings → Connections → Connect a bank: the kind question, then Link
    /// (against a local server without Plaid credentials, the error it shows).
    func testConnect() {
        sleep(4)
        tab("Settings")
        let connections = app.buttons.matching(NSPredicate(format: "label BEGINSWITH[c] 'Connections'")).firstMatch
        guard connections.waitForExistence(timeout: 3) else { return }
        connections.tap()
        sleep(3)
        app.buttons["Connect a bank"].firstMatch.tap()
        sleep(1)
        snap("30-connect-kind")
        let kind = app.buttons["Bank, card or loan"].firstMatch
        if kind.waitForExistence(timeout: 2) {
            kind.tap()
            sleep(5)
            snap("31-connect-result")
        }
    }

    /// Settings → Lock with Face ID, then leave and come back: the cover. Needs
    /// Face ID enrolled on the simulator (Features → Face ID → Enrolled).
    func testLock() {
        sleep(4)
        tab("Settings")
        snap("40-settings")
        let lock = app.switches.matching(NSPredicate(format: "label BEGINSWITH[c] 'Lock with'")).firstMatch
        guard lock.waitForExistence(timeout: 3) else { return }
        if lock.value as? String == "0" { lock.tap() }
        sleep(1)
        snap("41-lock-on")
        XCUIDevice.shared.press(.home)
        sleep(2)
        app.activate()
        sleep(2)
        snap("42-locked")
    }

    /// The wide layout (an iPad; the open iPhone Duo is the same size class): the
    /// panels in columns, a list beside what was picked in it, upright and on its side.
    func testWide() {
        guard app.windows.firstMatch.frame.width >= 600 else { return }
        sleep(5)
        for (o, orientation) in [("portrait", UIDeviceOrientation.portrait), ("landscape", .landscapeLeft)] {
            XCUIDevice.shared.orientation = orientation
            sleep(2)
            tab("Overview")
            snap("50-\(o)-overview")
            tab("Accounts")
            snap("51-\(o)-accounts")
            let account = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] '$'")).element(boundBy: 1)
            if account.waitForExistence(timeout: 3) { account.tap(); sleep(3) }
            snap("52-\(o)-account")
            tab("Activity")
            let row = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] '$'")).element(boundBy: 2)
            if row.waitForExistence(timeout: 3) { row.tap(); sleep(2) }
            snap("53-\(o)-transaction")
            if o == "portrait" {
                app.navigationBars.buttons["Edit"].firstMatch.tap()
                sleep(2)
                snap("54-\(o)-transaction-edit")
                app.buttons["Cancel"].firstMatch.tap()
                sleep(1)
            }
            tab("Insights")
            for (i, name) in ["Cash flow", "Spending", "Net worth & debt"].enumerated() {
                let b = app.buttons[name]
                if b.waitForExistence(timeout: 3) { b.tap() }
                sleep(4)
                snap("55-\(o)-insights-\(i)")
            }
            tab("Settings")
            snap("56-\(o)-settings")
        }
        XCUIDevice.shared.orientation = .portrait
    }

    private func tab(_ name: String) {
        // A phone's tab bar; an iPad's bar on top (where a tab that doesn't fit
        // hides behind its chevron).
        let bar = app.tabBars.buttons[name]
        if bar.exists, bar.isHittable { bar.tap() } else {
            // On its side the iPad shows a sidebar, whose tabs are cells.
            let candidates = [app.buttons[name].firstMatch, app.cells[name].firstMatch,
                              app.cells.containing(.staticText, identifier: name).firstMatch]
            if let hit = candidates.first(where: { $0.exists && $0.isHittable }) { hit.tap() }
        }
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
