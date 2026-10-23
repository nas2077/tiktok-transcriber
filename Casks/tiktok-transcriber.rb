# brew tap nas2077/tiktok-transcriber https://github.com/nas2077/tiktok-transcriber
# brew install --cask tiktok-transcriber
cask "tiktok-transcriber" do
  arch arm: "arm64", intel: "x64"

  version "0.2.1"
  sha256 arm:   "6badd64d813d8598f70fbfb597f3092d63ba0d177022eb72d7bb51159ee43e76",
         intel: "78531d5e834cefa91cc22d5420c88e6d5e07264952bf744d2f4d36393dbfc438"

  url "https://github.com/nas2077/tiktok-transcriber/releases/download/v#{version}/TikTok-Transcriber-#{version}-macos-#{arch}.dmg"
  name "TikTok Transcriber"
  desc "Readable transcripts from public TikTok clips and profiles, recognized locally"
  homepage "https://github.com/nas2077/tiktok-transcriber"

  livecheck do
    url :url
    strategy :github_latest
  end

  depends_on macos: ">= :big_sur"

  app "TikTok Transcriber.app"

  zap trash: "~/Library/Application Support/TikTok Transcriber"

  caveats <<~EOS
    TikTok Transcriber is not signed with an Apple Developer ID. If macOS refuses to open
    it the first time, open System Settings > Privacy & Security and choose
    "Open Anyway" for TikTok Transcriber.
  EOS
end
