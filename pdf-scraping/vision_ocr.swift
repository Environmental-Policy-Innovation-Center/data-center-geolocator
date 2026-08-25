import Foundation
import ImageIO
import Vision

struct OCRBox: Codable {
    let text: String
    let confidence: Float
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

struct OCRPage: Codable {
    let image: String
    let pixelWidth: Int
    let pixelHeight: Int
    let observations: [OCRBox]
}

guard CommandLine.arguments.count == 3 else {
    FileHandle.standardError.write(Data("usage: vision_ocr INPUT_DIR OUTPUT_JSONL\n".utf8))
    exit(2)
}

let inputDirectory = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2])
let manager = FileManager.default
let imageURLs = try manager.contentsOfDirectory(
    at: inputDirectory,
    includingPropertiesForKeys: nil,
    options: [.skipsHiddenFiles]
).filter { ["png", "jpg", "jpeg", "tif", "tiff"].contains($0.pathExtension.lowercased()) }
 .sorted { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }

manager.createFile(atPath: outputURL.path, contents: nil)
let output = try FileHandle(forWritingTo: outputURL)
defer { try? output.close() }
let encoder = JSONEncoder()

for (index, imageURL) in imageURLs.enumerated() {
    autoreleasepool {
        guard let source = CGImageSourceCreateWithURL(imageURL as CFURL, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            FileHandle.standardError.write(Data("Could not read \(imageURL.path)\n".utf8))
            return
        }

        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        request.recognitionLanguages = ["en-US"]
        request.customWords = ["Equinix", "IEPA", "NOx", "SO2", "PM10", "PM2.5", "VOM", "FESOP", "NESHAP", "NSPS"]
        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        do {
            try handler.perform([request])
        } catch {
            let nsError = error as NSError
            FileHandle.standardError.write(Data("Vision failed for \(imageURL.path): \(nsError.domain) \(nsError.code)\n".utf8))
            return
        }

        let boxes: [OCRBox] = (request.results ?? []).compactMap { observation in
            guard let candidate = observation.topCandidates(1).first else { return nil }
            let box = observation.boundingBox
            return OCRBox(
                text: candidate.string,
                confidence: candidate.confidence,
                x: box.origin.x,
                y: box.origin.y,
                width: box.size.width,
                height: box.size.height
            )
        }
        let page = OCRPage(
            image: imageURL.lastPathComponent,
            pixelWidth: image.width,
            pixelHeight: image.height,
            observations: boxes
        )
        do {
            output.write(try encoder.encode(page))
            output.write(Data("\n".utf8))
        } catch {
            FileHandle.standardError.write(Data("Could not encode \(imageURL.path): \(error)\n".utf8))
        }
        FileHandle.standardError.write(Data("[\(index + 1)/\(imageURLs.count)] \(imageURL.lastPathComponent): \(boxes.count) lines\n".utf8))
    }
}
