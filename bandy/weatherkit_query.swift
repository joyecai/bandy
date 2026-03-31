import Foundation
import WeatherKit
import CoreLocation

let args = CommandLine.arguments
guard args.count >= 4 else {
    print("{\"error\":\"usage: weatherkit_query <lat> <lon> <day_offset>\"}")
    exit(1)
}

guard let lat = Double(args[1]), let lon = Double(args[2]), let dayOff = Int(args[3]) else {
    print("{\"error\":\"invalid arguments\"}")
    exit(1)
}

let service = WeatherService.shared
let location = CLLocation(latitude: lat, longitude: lon)
let semaphore = DispatchSemaphore(value: 0)

Task {
    do {
        let weather = try await service.weather(for: location)
        var info: [String: Any]
        if dayOff == 0 {
            let c = weather.currentWeather
            info = [
                "type": "current",
                "temp": round(c.temperature.value * 10) / 10,
                "condition": "\(c.condition)",
                "humidity": Int(c.humidity * 100),
                "wind_kph": round(c.wind.speed.converted(to: .kilometersPerHour).value * 10) / 10,
                "uv": c.uvIndex.value
            ]
        } else {
            let forecasts = weather.dailyForecast.forecast
            guard dayOff < forecasts.count else {
                print("{\"error\":\"day_offset out of range\"}")
                semaphore.signal()
                return
            }
            let d = forecasts[dayOff]
            info = [
                "type": "forecast",
                "high": round(d.highTemperature.value * 10) / 10,
                "low": round(d.lowTemperature.value * 10) / 10,
                "condition": "\(d.condition)",
                "precip_chance": Int(d.precipitationChance * 100),
                "uv": d.uvIndex.value
            ]
        }
        let data = try JSONSerialization.data(withJSONObject: info, options: [])
        print(String(data: data, encoding: .utf8)!)
    } catch {
        print("{\"error\":\"\(error.localizedDescription)\"}")
    }
    semaphore.signal()
}
semaphore.wait()
