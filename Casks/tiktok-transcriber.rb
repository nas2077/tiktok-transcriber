# brew tap nas2077/tiktok-transcriber https://github.com/nas2077/tiktok-transcriber
# brew install --cask tiktok-transcriber
cask "tiktok-transcriber" do
  arch arm: "arm64", intel: "x64"

  version "0.2.2"
  sha256 arm:   "3e5a9a13ed3f7893bf9cf4d31f992d9cec71c61eb8b17d2fa266d4ea56892f39",
         intel: "44137aeb922a5f476962638b248d160d1783df29a3af703449d58379cdd32914"

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
