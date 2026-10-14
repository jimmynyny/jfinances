import Foundation

/// The server sends money and quantities as decimal strings ("1234.56") and
/// ratios as numbers (docs/80). These wrappers take either, so a model can say
/// `@Flex var amount: Double` and not care which arrived.
///
/// Doubles are fine here: this side only formats and draws. The arithmetic
/// that matters (sums, balances) is done in `numeric` on the server.
@propertyWrapper
public struct Flex: Codable, Hashable, Sendable {
    public var wrappedValue: Double
    public init(wrappedValue: Double) { self.wrappedValue = wrappedValue }

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { wrappedValue = 0; return }
        if let d = try? c.decode(Double.self) { wrappedValue = d; return }
        if let s = try? c.decode(String.self), let d = Double(s) { wrappedValue = d; return }
        throw DecodingError.dataCorruptedError(in: c, debugDescription: "expected a number or a decimal string")
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        try c.encode(wrappedValue)
    }
}

/// `Flex`, where null (or a missing key) means "not known" rather than zero.
@propertyWrapper
public struct FlexOpt: Codable, Hashable, Sendable {
    public var wrappedValue: Double?
    public init(wrappedValue: Double?) { self.wrappedValue = wrappedValue }

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { wrappedValue = nil; return }
        if let d = try? c.decode(Double.self) { wrappedValue = d; return }
        if let s = try? c.decode(String.self) { wrappedValue = Double(s); return }
        wrappedValue = nil
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        if let wrappedValue { try c.encode(wrappedValue) } else { try c.encodeNil() }
    }
}

public extension KeyedDecodingContainer {
    // A missing key decodes as zero / nil instead of failing the whole response:
    // an older server that lacks a field should still draw.
    func decode(_ type: Flex.Type, forKey key: Key) throws -> Flex {
        try decodeIfPresent(type, forKey: key) ?? Flex(wrappedValue: 0)
    }

    func decode(_ type: FlexOpt.Type, forKey key: Key) throws -> FlexOpt {
        try decodeIfPresent(type, forKey: key) ?? FlexOpt(wrappedValue: nil)
    }
}

/// Any JSON value, for the few responses whose keys are data (net worth by
/// kind: one key per group).
public enum JSONValue: Codable, Hashable, Sendable {
    case string(String), number(Double), bool(Bool), object([String: JSONValue]), array([JSONValue]), null

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let b = try? c.decode(Bool.self) { self = .bool(b) }
        else if let d = try? c.decode(Double.self) { self = .number(d) }
        else if let s = try? c.decode(String.self) { self = .string(s) }
        else if let a = try? c.decode([JSONValue].self) { self = .array(a) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let s): try c.encode(s)
        case .number(let d): try c.encode(d)
        case .bool(let b): try c.encode(b)
        case .object(let o): try c.encode(o)
        case .array(let a): try c.encode(a)
        case .null: try c.encodeNil()
        }
    }

    public var number: Double? {
        switch self {
        case .number(let d): return d
        case .string(let s): return Double(s)
        default: return nil
        }
    }

    public var string: String? {
        if case .string(let s) = self { return s }
        return nil
    }
}

public enum JSON {
    public static let decoder = JSONDecoder()
    public static let encoder = JSONEncoder()
}
