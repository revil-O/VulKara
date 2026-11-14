// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The subject of a picture as a mask, by Apple Vision (VNGenerateForegroundInstanceMaskRequest, macOS 14 and later,
// on this Mac, nothing to download). All subjects found are merged into one mask in the picture's own size and
// orientation: white = subject, black = the rest, soft at the edges. With a second file and more than one subject,
// that file gets which subject each pixel belongs to (grey 1..n, 0 = none), in the same size, so the app can take
// single subjects out of the mask.
//
//   subject-mask <picture> <mask.png> [<labels.png>]
//   subject-mask --persons <picture> <labels.png>
//
// With --persons only the people (VNGeneratePersonInstanceMaskRequest, up to four; more may be missed or merged) as
// a map: grey 1..n where a person's own mask is at least half and strongest, 0 elsewhere; prints "persons <n>".
// Remove (ObjectClear) leaves the people that are not painted as they are.
//
// Prints "subjects <n>" to stdout. Exit codes: 0 done, 2 wrong call, 3 the picture can not be read, 4 no subject
// found, 5 Vision or writing the mask failed (the subjects' map not written: "subjects 1", exit 0). The message for
// the log goes to stderr (English; the app shows its own text).

import CoreVideo
import Foundation
import ImageIO
import UniformTypeIdentifiers
import Vision

func fail(_ message: String, _ code: Int32) -> Never {
  FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
  exit(code)
}

var args = CommandLine.arguments
let persons = args.count == 4 && args[1] == "--persons"
if persons { args.remove(at: 1) }
guard args.count == 3 || args.count == 4 else {
  fail("usage: subject-mask <picture> <mask.png> [<labels.png>] | subject-mask --persons <picture> <labels.png>", 2)
}

// the picture turned upright as its EXIF orientation says, in full size (as the app shows it)
guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: args[1]) as CFURL, nil),
      let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
      let w = props[kCGImagePropertyPixelWidth] as? Int, let h = props[kCGImagePropertyPixelHeight] as? Int,
      let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [
        kCGImageSourceCreateThumbnailFromImageAlways: true,
        kCGImageSourceCreateThumbnailWithTransform: true,
        kCGImageSourceThumbnailMaxPixelSize: max(w, h),
      ] as CFDictionary)
else { fail("The picture can not be read", 3) }

let handler = VNImageRequestHandler(cgImage: image, orientation: .up)
let found: VNInstanceMaskObservation
do {
  let first: VNInstanceMaskObservation?
  if persons {
    let request = VNGeneratePersonInstanceMaskRequest()
    try handler.perform([request])
    first = request.results?.first
  } else {
    let request = VNGenerateForegroundInstanceMaskRequest()
    try handler.perform([request])
    first = request.results?.first
  }
  guard let first, !first.allInstances.isEmpty else { fail(persons ? "No person found" : "No subject found", 4) }
  found = first
} catch {
  fail("Vision: \(error.localizedDescription)", 5)
}

/// The mask of these subjects in the picture's size, one float (0..1) per pixel: body gets its width, its height and
/// a row by its index.
func withScaledMask(_ instances: IndexSet, _ body: (_ w: Int, _ h: Int, _ row: (Int) -> UnsafePointer<Float32>) -> Void) {
  let mask: CVPixelBuffer
  do {
    mask = try found.generateScaledMaskForImage(forInstances: instances, from: handler)
  } catch {
    fail("Vision: \(error.localizedDescription)", 5)
  }
  CVPixelBufferLockBaseAddress(mask, .readOnly)
  defer { CVPixelBufferUnlockBaseAddress(mask, .readOnly) }
  let rowBytes = CVPixelBufferGetBytesPerRow(mask)
  guard CVPixelBufferGetPixelFormatType(mask) == kCVPixelFormatType_OneComponent32Float,
        let base = CVPixelBufferGetBaseAddress(mask)
  else { fail("Vision: unexpected mask format", 5) }
  body(CVPixelBufferGetWidth(mask), CVPixelBufferGetHeight(mask)) { y in UnsafePointer((base + y * rowBytes).assumingMemoryBound(to: Float32.self)) }
}

/// false when the file can not be written
func writeGrey(_ grey: [UInt8], _ mw: Int, _ mh: Int, _ path: String) -> Bool {
  guard let provider = CGDataProvider(data: Data(grey) as CFData),
        let out = CGImage(width: mw, height: mh, bitsPerComponent: 8, bitsPerPixel: 8, bytesPerRow: mw,
                          space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGBitmapInfo(rawValue: 0),
                          provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent),
        let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: path) as CFURL, UTType.png.identifier as CFString, 1, nil)
  else { return false }
  CGImageDestinationAddImage(dest, out, nil)
  return CGImageDestinationFinalize(dest)
}

/// 0..1 → 0..255
@inline(__always) func byte(_ v: Float32) -> UInt8 { UInt8(max(0, min(255, v * 255 + 0.5))) }

/// Each pixel to the instance whose own mask is strongest there (exact at the soft edges, unlike Vision's coarse
/// map), where that is above least; w × h is the picture's size (0 = take the first mask's).
func labelMap(_ least: UInt8, _ mw: inout Int, _ mh: inout Int) -> [UInt8] {
  var strongest = [UInt8](), labels = [UInt8]()
  // one mask at a time (96 MB as floats at 24 MP): each let go before the next
  for instance in found.allInstances { autoreleasepool {
    let label = UInt8(min(instance, 255))
    withScaledMask(IndexSet(integer: instance)) { w, h, row in
      if strongest.isEmpty {
        if mw == 0 { (mw, mh) = (w, h) }
        strongest = [UInt8](repeating: least, count: mw * mh)
        labels = [UInt8](repeating: 0, count: mw * mh)
      }
      guard w == mw, h == mh else { fail("Vision: masks of different sizes", 5) }
      for y in 0..<h {
        let r = row(y)
        for x in 0..<w {
          let v = byte(r[x])
          if v > strongest[y * w + x] { strongest[y * w + x] = v; labels[y * w + x] = label }
        }
      }
    }
  } }
  return labels
}

var (mw, mh) = (0, 0)
if persons {
  // a person counts where its own mask is at least half
  guard writeGrey(labelMap(127, &mw, &mh), mw, mh, args[2]) else { fail("The persons' map can not be written", 5) }
  print("persons \(found.allInstances.count)")
  exit(0)
}

// all subjects in one mask
withScaledMask(found.allInstances) { w, h, row in
  (mw, mh) = (w, h)
  var grey = [UInt8](repeating: 0, count: w * h)
  for y in 0..<h {
    let r = row(y)
    for x in 0..<w { grey[y * w + x] = byte(r[x]) }
  }
  guard writeGrey(grey, w, h, args[2]) else { fail("The mask can not be written", 5) }
}

var subjects = found.allInstances.count
if args.count == 4 && subjects > 1 {
  let labels = labelMap(0, &mw, &mh)
  // the mask is valid without it: then it is one selection that can not be split into subjects
  if !writeGrey(labels, mw, mh, args[3]) {
    FileHandle.standardError.write("The subjects' map can not be written, one selection instead\n".data(using: .utf8)!)
    try? FileManager.default.removeItem(atPath: args[3])
    subjects = 1
  }
}
print("subjects \(subjects)")
