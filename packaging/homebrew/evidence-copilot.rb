cask "evidence-copilot" do
  version "0.1.0"
  sha256 :no_check

  arch arm: "arm64", intel: "x64"

  url "https://github.com/LawrenceLiu2005/MedCopilot/releases/download/desktop-v#{version}/EvidenceCopilot-mac-#{arch}.dmg"
  name "Evidence Copilot"
  desc "傻瓜式医学科研 Agent（Pi 官方内核 + PubMed 侧车）"
  homepage "https://github.com/LawrenceLiu2005/MedCopilot"

  app "Evidence Copilot.app"

  zap trash: [
    "~/Library/Application Support/EvidenceCopilot",
  ]
end
