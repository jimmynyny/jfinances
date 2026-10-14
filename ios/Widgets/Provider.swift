import AppIntents
import JFinancesKit
import WidgetKit

struct GlanceEntry<I: AmountsIntent>: TimelineEntry {
    enum Status { case live, stale, notLinked }
    let date: Date
    let glance: Glance?
    let fetchedAt: Date?
    let status: Status
    let configuration: I
}

/// Every widget draws from one glance (`GET /glance`), cached on disk so
/// widgets refreshing together make one request, and so an offline phone
/// still shows the last figures with their time.
struct GlanceProvider<I: AmountsIntent>: AppIntentTimelineProvider {
    typealias Entry = GlanceEntry<I>
    typealias Intent = I

    func placeholder(in context: Context) -> Entry {
        Entry(date: Date(), glance: SampleGlance.glance, fetchedAt: Date(), status: .live, configuration: I())
    }

    func snapshot(for configuration: I, in context: Context) async -> Entry {
        if context.isPreview, GlanceCache.load() == nil {
            return Entry(date: Date(), glance: SampleGlance.glance, fetchedAt: Date(), status: .live, configuration: configuration)
        }
        return await entry(configuration, maxAge: 600)
    }

    func timeline(for configuration: I, in context: Context) async -> Timeline<Entry> {
        let e = await entry(configuration, maxAge: 300)
        // Every 30 minutes: well inside WidgetKit's daily budget. The app also
        // asks for a reload whenever it refreshes.
        return Timeline(entries: [e], policy: .after(Date().addingTimeInterval(30 * 60)))
    }

    private func entry(_ configuration: I, maxAge: TimeInterval) async -> Entry {
        guard Keychain.read() != nil else {
            return Entry(date: Date(), glance: nil, fetchedAt: nil, status: .notLinked, configuration: configuration)
        }
        let (cached, error) = await GlanceCache.fetch(maxAge: maxAge)
        if error?.tokenIsDead == true {
            return Entry(date: Date(), glance: nil, fetchedAt: nil, status: .notLinked, configuration: configuration)
        }
        return Entry(date: Date(), glance: cached?.glance, fetchedAt: cached?.fetchedAt,
                     status: error == nil ? .live : .stale, configuration: configuration)
    }
}
