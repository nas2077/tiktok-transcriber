# brew tap nas2077/tiktok-transcriber https://github.com/nas2077/tiktok-transcriber
# brew install --cask tiktok-transcriber
cask "tiktok-transcriber" do
  arch arm: "arm64", intel: "x64"

  version "0.2.0"
  sha256 arm:   "72ed045d3e42f800903d0ea0e315f650581d0bcaa7636f5720b2bc8c0ac485bf",
         intel: "d05dafc883dbe5326586ade3137ad071fd2be711bf37ec0cd16845d2c1ba00d2"

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
