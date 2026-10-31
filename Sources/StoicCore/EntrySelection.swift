import Foundation

public enum EntrySelection {
    public static func selecting(_ id: String, in orderedIDs: [String], selected: Set<String>, anchor: String?, extending: Bool, toggling: Bool) -> Set<String> {
        guard let target = orderedIDs.firstIndex(of: id) else { return selected }
        if extending, let anchor, let origin = orderedIDs.firstIndex(of: anchor) {
            let range = Set(orderedIDs[min(origin, target)...max(origin, target)])
            return toggling ? selected.union(range) : range
        }
        if toggling {
            return selected.contains(id) ? selected.subtracting([id]) : selected.union([id])
        }
        return [id]
    }
}
