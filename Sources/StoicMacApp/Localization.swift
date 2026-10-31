import Foundation
import StoicCore

@MainActor
func L(_ source: String) -> String { AppLocalization.text(source, language: currentLanguage) }

@MainActor
func LF(_ source: String, _ arguments: CVarArg...) -> String {
    String(format: L(source), locale: currentLanguage.locale, arguments: arguments)
}

@MainActor
var currentLanguage: AppLanguage {
    AppLanguage(rawValue: UserDefaults.standard.string(forKey: "appLanguage") ?? "ru") ?? .russian
}
